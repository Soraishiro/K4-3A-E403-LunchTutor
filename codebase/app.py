"""
Lunch Tutorial — Codebase Application Runner (CP3 Prototype)

Usage:
  # 1. Start interactive Web UI (for 30s screen recording & live testing):
  python codebase/app.py --web --port 8000

  # 2. Interactive CLI Mode:
  python codebase/app.py

  # 3. Direct Single Turn Query:
  python codebase/app.py --query "Cho tôi đáp án của lab03"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# Ensure UTF-8 output on Windows
for stream in (sys.stdout, sys.stderr):
    if stream and hasattr(stream, "reconfigure") and (not stream.encoding or stream.encoding.lower() != "utf-8"):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

CODEBASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CODEBASE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from codebase.decision_core import CentralDecisionEngine, DecisionOutcome
from codebase.tools import (
    ALLOWLIST_PUBLIC_PATHS,
    ToolRegistry,
    filter_visible_chunks,
    is_publishable,
    load_chunk_index,
    load_env_api_key,
    normalize_rel_path,
    search_sources,
)
from codebase.models import SessionState, create_session, get_session, update_session, QuestionKind, HintLevel
from codebase.coach import get_coach_feedback, CoachClient
from codebase.quiz import get_questions, get_question, record_attempt, get_question_result, get_quiz_summary
from codebase.ingest import scan_sources
from codebase import labs

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def _fallback_api_key() -> str:
    return load_env_api_key()


# Lab Simulator MVP state
LAB3_OBJECTIVE = "Xây dựng ReAct Agent với Native Tool Calling: khai báo Tool Schema, sửa Truncated Loop, xuất Waterfall Trace"
_GENERATED_DIR = PROJECT_ROOT / "data" / "generated" / "day03"
_TOOL_REGISTRY: ToolRegistry | None = None
_COACH_CLIENT: CoachClient | None = None


def _get_tool_registry() -> ToolRegistry:
    global _TOOL_REGISTRY
    if _TOOL_REGISTRY is None:
        _TOOL_REGISTRY = ToolRegistry(_GENERATED_DIR)
    return _TOOL_REGISTRY


def _get_coach_client() -> CoachClient | None:
    global _COACH_CLIENT
    if _COACH_CLIENT is None:
        api_key = os.getenv("OPENAI_API_KEY") or _fallback_api_key()
        if api_key:
            _COACH_CLIENT = CoachClient(api_key)
    return _COACH_CLIENT


def _load_bundle_evidence() -> list:
    """Load evidence from chunks for coach context."""
    from codebase.models import Evidence, SourceRef, SourceKind
    chunks_path = _GENERATED_DIR / "source_chunks.jsonl"
    if not chunks_path.exists():
        return []
    chunks = load_chunk_index(chunks_path)
    evidence_list = []
    for chunk in chunks:
        if chunk.get("lab_id") != "day03":
            continue
        evidence_list.append(Evidence(
            evidence_id=chunk.get("chunk_id"),
            title=chunk.get("path", "").split("/")[-1],
            excerpt=chunk.get("text", "")[:500],
            source=SourceRef(
                path=chunk.get("path", ""),
                start_line=chunk.get("start_line", 0),
                end_line=chunk.get("end_line", 0),
                sha256=chunk.get("sha256", "")
            ),
            source_kind=SourceKind(chunk.get("source_kind", "reported"))
        ))
    return evidence_list


# ---------------------------------------------------------------------------
# Grounded Q&A + Evidence (per-chunk retrieval, per-citation verification)
# ---------------------------------------------------------------------------
QA_CHUNKS_PATH = PROJECT_ROOT / "data" / "generated" / "day03" / "source_chunks.jsonl"
QA_MANIFEST_PATH = PROJECT_ROOT / "data" / "generated" / "day03" / "source_manifest.json"
_QA_INDEX_CACHE: list[dict[str, Any]] | None = None


def _get_qa_index() -> list[dict[str, Any]]:
    global _QA_INDEX_CACHE
    if _QA_INDEX_CACHE is None:
        _QA_INDEX_CACHE = load_chunk_index(QA_CHUNKS_PATH)
    return _QA_INDEX_CACHE


def _to_evidence(chunk: dict[str, Any], snippet_len: int = 300) -> dict[str, Any]:
    text = chunk.get("text", "")
    sha = chunk.get("sha256", "")
    return {
        "chunk_id": chunk.get("chunk_id"),
        "path": chunk.get("path"),
        "start_line": chunk.get("start_line"),
        "end_line": chunk.get("end_line"),
        "source_kind": chunk.get("source_kind"),
        "sha256": sha,
        "sha_short": sha[:10],
        "snippet": text[:snippet_len] + ("..." if len(text) > snippet_len else ""),
    }


def _verify_citations(citations: list[str], retrieved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map each LLM-returned citation to a real retrieved chunk.

    Only citations exactly matching a retrieved chunk_id (or the
    path:start-end of a retrieved chunk) pass. Everything else is dropped —
    no hallucinated citations allowed.
    """
    by_id = {r.get("chunk_id"): r for r in retrieved}
    by_ref = {f"{r.get('path')}:{r.get('start_line')}-{r.get('end_line')}": r for r in retrieved}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in citations or []:
        c = str(c).strip()
        chunk = by_id.get(c) or by_ref.get(c)
        if chunk and chunk.get("chunk_id") not in seen:
            seen.add(chunk["chunk_id"])
            ev = _to_evidence(chunk)
            ev["ref"] = f"{ev['path']}:{ev['start_line']}-{ev['end_line']}"
            ev["verified"] = True
            out.append(ev)
    return out


def answer_qa(query: str, top_k: int = 5) -> dict[str, Any]:
    """Grounded Q&A over ingested docs+code.

    Publish policy is enforced BEFORE retrieval reaches the provider: only
    visible (publishable + manifest-bound + snapshot-current) chunks enter
    the prompt, the evidence list, and citation matching. `evidence` is what
    was retrieved; `model_citations` is what the model claimed;
    `citations_verified` is the proven intersection. Search results are never
    auto-promoted to model citations.
    """
    empty = {
        "query": query,
        "answer": "",
        "citations": [],
        "citations_verified": [],
        "model_citations": [],
        "citation_note": "",
        "evidence": [],
        "retrieved_count": 0,
        "model": "mock",
        "provider_status": "mock",
    }
    if not QA_CHUNKS_PATH.exists() or not QA_MANIFEST_PATH.exists():
        return {
            **empty,
            "answer": "Không tìm thấy dữ liệu Lab 3. Hãy chạy ingest.py trước.",
        }
    index = _get_qa_index()
    manifest = _manifest_by_path()
    retrieved_raw = search_sources(index, "day03", query, top_k=max(top_k * 3, top_k))
    retrieved = filter_visible_chunks(retrieved_raw, manifest, snapshot_ok)
    evidence = [_to_evidence(r) for r in retrieved[:top_k]]
    context = "\n".join(f"[{r.get('chunk_id')}] {r.get('text', '')[:500]}" for r in retrieved[:top_k])

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY", "") or _fallback_api_key()
    if not api_key:
        return {
            **empty,
            "answer": "[Chế độ Mock] Bạn cần cung cấp GEMINI_API_KEY hoặc OPENAI_API_KEY để dùng LLM thật.",
            "evidence": evidence,
            "retrieved_count": len(evidence),
            "citation_note": "mock mode: model chưa được gọi",
        }

    from codebase.engine import get_provider
    provider_name = "gemini" if (os.getenv("GEMINI_API_KEY") or api_key.startswith("AIza")) else "openai"
    provider = get_provider(provider_name, api_key=api_key)
    system_msg = (
        "Bạn là trợ lý AI học tập LabPath. Chỉ trả lời dựa trên TÀI LIỆU được cung cấp dưới đây. "
        "Mỗi khẳng định factual phải trích dẫn chunk_id NGUYÊN VĂN (ví dụ 'src/app.py:36-75'). "
        "Trả về JSON duy nhất: {\"answer\": \"...\", \"citations\": [\"<chunk_id>\", ...]}. "
        "Nếu tài liệu không đủ căn cứ, nói 'không chắc' và đề nghị học viên đọc tài liệu."
    )
    user_msg = f"Câu hỏi: {query}\n\nTài liệu tham khảo (retrieved):\n{context[:3000]}"
    model_citations: list[str] = []
    try:
        resp = provider.complete([{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}])
        raw_text = resp.text or ""
        try:
            data = json.loads(raw_text)
            response_text = data.get("answer", raw_text)
            model_citations = [str(c) for c in (data.get("citations", []) or [])]
        except json.JSONDecodeError:
            response_text = raw_text
        model_used = getattr(provider, "model", provider_name)
    except Exception as e:
        response_text = f"[Lỗi gọi LLM: {e}] — Dùng chế độ mock."
        model_used = "mock"

    verified = _verify_citations(model_citations, retrieved)
    note = "" if verified else "Model không dẫn nguồn hợp lệ — chỉ dùng chunk truy xuất để đối chiếu."
    return {
        "query": query,
        "answer": response_text,
        "citations": [v["ref"] for v in verified],
        "citations_verified": verified,
        "model_citations": model_citations,
        "citation_note": note,
        "evidence": evidence,
        "retrieved_count": len(evidence),
        "model": model_used,
        "provider_status": "live" if model_used != "mock" else "mock",
    }


# ---------------------------------------------------------------------------
# Socratic Lab Tutor — multi-turn conversation, real LLM (Task 1.1 Agentic Fit)
# ---------------------------------------------------------------------------
_LAB_SECTIONS_CACHE: dict[str, list[str]] | None = None


def _lab_sections() -> dict[str, list[str]]:
    """Markdown headings actually present in each allowlisted lab doc.

    The coach may point a learner at a file and a section; both are checked
    against the real repo so a refusal never sends someone to a heading that
    does not exist.
    """
    global _LAB_SECTIONS_CACHE
    if _LAB_SECTIONS_CACHE is not None:
        return _LAB_SECTIONS_CACHE
    sections: dict[str, list[str]] = {}
    for rel in ALLOWLIST_PUBLIC_PATHS:
        if not rel.endswith(".md"):
            continue
        target = PUBLIC_LAB_DIR / rel
        try:
            text = target.read_text(encoding="utf-8")
        except OSError:
            continue
        heads = [
            line.lstrip("#").strip()
            for line in text.splitlines()
            if line.startswith("#")
        ]
        sections[rel] = [h for h in heads if h]
    _LAB_SECTIONS_CACHE = sections
    return sections


def _task_headings() -> str:
    """The Task headings, verbatim, for the prompt's allowed-pointer list."""
    heads = _lab_sections().get("docs/CODELAB.md", [])
    return "\n".join("  - " + h for h in heads if "TASK" in h.upper())


MENTOR_SOCRATIC_PROMPT = """Bạn là AI Socratic Coach của Bài Lab 3 AI20k (Chatbot vs ReAct Agent).

VIỆC CỦA BẠN KHÔNG PHẢI CHẤM ĐÚNG/SAI.
Việc của bạn là làm cho học viên tự nhìn thấy LẬP LUẬN CỦA HỌ HỎNG TRONG ĐIỀU KIỆN NÀO,
rồi giao lại một việc cụ thể họ phải TỰ CODE trong Lab để kiểm chứng.

TUYỆT ĐỐI CẤM:
- Nói "đáp án của bạn đúng" / "bạn trả lời sai" / "chính xác rồi" / xác nhận một lựa chọn là chuẩn.
- Loại dần các lựa chọn cho đến khi chỉ còn một.
- Viết code hộ, đưa full patch, hoặc nói thẳng nên chọn kiến trúc nào.
Không có lựa chọn nào ở Task 1.1 là đáp án đúng sẵn. Chatbot/RAG, ReAct Agent, backend quy
trình xác định, hay "chưa đủ thông tin" — mỗi cái đều đứng vững hoặc sụp đổ tuỳ điều kiện.
Việc của bạn là tìm ra điều kiện đó.

NƯỚC ĐI ƯU TIÊN CAO NHẤT — KIỂM TRA TRƯỚC MỌI NƯỚC KHÁC:
0. refuse_and_redirect — dùng NGAY khi học viên xin đáp án, xin full code, nhờ làm hộ, giục
   vì "nộp gấp", hoặc bảo bạn chọn kiến trúc thay họ.
   Cách làm ĐÚNG, theo đúng thứ tự, không thêm gì khác:
   (a) Từ chối thẳng trong MỘT câu. Không giảng đạo đức, không dài dòng, không xin lỗi.
   (b) Chỉ CHÍNH XÁC chỗ cần đọc trong Lab: tên file + mục, và đọc để trả lời câu hỏi gì.
   (c) Một câu hỏi duy nhất đưa họ trở lại tự suy nghĩ.
   Tuyệt đối KHÔNG lờ đi việc họ đang xin bài rồi hỏi sang chuyện khác. Phải từ chối trước.
   BẮT BUỘC ĐỔI CÁCH DIỄN ĐẠT MỖI LẦN. Không dùng lại một câu từ chối mẫu. Câu từ chối phải
   bám vào đúng thứ họ vừa xin (xin full code khác xin chọn kiến trúc hộ khác giục nộp gấp),
   và chỗ đọc phải khớp Task họ đang mắc, không phải mặc định Task 1.1.
   Tên mục trong reading_pointer.section phải COPY CHÍNH XÁC từ danh sách heading bên dưới —
   không rút gọn, không diễn đạt lại, không tự đặt tên mục mới.

CÁC CHỖ ĐỌC CÓ THẬT TRONG REPO LAB (chỉ được trỏ vào những chỗ này, không bịa file khác):
- docs/CODELAB.md — mục "TASK 1.1 — ĐÁNH GIÁ 4 TIÊU CHÍ AGENTIC FIT" (vì sao đánh giá trước khi code)
- docs/CODELAB.md — mục "TASK 1.2 — KHAI BÁO TOOL SCHEMAS CHUẨN JSON SCHEMA"
- docs/DANH_SACH_DE_TAI.md — danh sách đề tài theo lĩnh vực
- docs/trace_eval.md — bảng Agentic Fit Scoring Matrix phải nộp
- docs/SO_TAY_THUC_HANH.md — checklist theo mốc thời gian, Checkpoint 1
- config/test_cases.json — nơi tự viết TC03, TC04, TC05
- src/tools.py — Tool Schema và dispatcher
- src/app.py — vòng lặp ReAct
- docs/trace_waterfall.json — trace Thought/Action/Observation
- README.md — quickstart, môi trường, cơ cấu điểm

BỐN NƯỚC ĐI CÒN LẠI, MỖI LƯỢT DÙNG ĐÚNG MỘT:
1. probe_assumption — chất vấn giả định ẩn sau lựa chọn của họ.
   Ví dụ khi họ chọn ReAct Agent vì "cần tra cứu dữ liệu": "Nếu một API duy nhất đã kiểm tra
   và trả về kết quả điều kiện tốt nghiệp, thì việc cần dữ liệu bên ngoài có còn đủ để chứng
   minh phải dùng ReAct không?"
2. counterfactual — đổi MỘT điều kiện để thử độ vững của lập luận, rồi hỏi quyết định của họ
   thay đổi ở ĐIỂM NÀO. Ví dụ: "Giả sử API đó chỉ trả số tín chỉ đã tích luỹ, còn điều kiện
   tốt nghiệp phải lấy từ nguồn khác."
3. ledger_update — sau khi họ phản biện: ghi nhận điều gì trong lập luận ĐÃ DỊCH CHUYỂN và
   điều gì VẪN CHƯA ĐƯỢC CHỨNG MINH. Nếu họ đang đánh đồng "nhiều bước xử lý" với "nhất
   thiết phải dùng LLM agent", hỏi ngược lại chỗ đó.
4. handoff_to_practice — khi lỗ hổng đã lộ rõ: gọi tên khái niệm cần xem lại và giao MỘT việc
   họ tự làm trong Lab.

QUY TẮC VỀ "GIẢ SỬ":
Mọi điều kiện bạn đặt ra ở nước đi counterfactual là PHẢN VÍ DỤ ĐỂ SUY NGHĨ. Chúng không phải
dữ kiện được khẳng định về mã nguồn Lab hay hệ thống học vụ thật. Đừng mô tả chúng như sự thật
đã xác minh, và đừng bịa ra nội dung file/dòng code cụ thể.

TRÌNH TỰ LAB (chỉ nâng bậc khi lập luận ở bậc hiện tại đã đứng vững):
- 1.1 Agentic Fit — 4 tiêu chí chính thức: Multi-step Reasoning, Tool Interaction,
  Dynamic Decision, Long Horizon Goal. Dùng ĐÚNG bốn tên này, không tự thay tiêu chí khác.
- 1.2 Tool Schema — khai báo 'required' đã đủ bảo đảm arguments hợp lệ chưa? Còn thiếu ràng
  buộc gì (kiểu dữ liệu, định dạng datetime, enum), và validate ở lớp nào?
- 2.1 Dispatcher — model gọi sai tên tool thì chặn ở đâu? Lỗi arguments bắt ở lớp nào?
- 2.2 ReAct Loop — có vòng while đã chứng minh multi-step chạy chưa? Observation đi đâu?
- 3.1 Trace — câu trả lời cuối "có vẻ đúng" nhưng Waterfall trace thiếu bước Observation thì
  kết luận được tới đâu?

VIỆC TỰ LÀM (practice_task) phải là thao tác kiểm chứng được trong Lab, không phải lời khuyên
chung chung. Ví dụ đạt yêu cầu: "Thêm vào config/test_cases.json một test case mà backend quy
trình cố định trả lời được và một test case mà nó trả lời sai; chạy cả hai rồi tự giải thích
chênh lệch trong ô giải trình Multi-step Reasoning của Scoring Matrix."

GIỌNG: tiếng Việt, đồng hành nhưng không nhượng bộ, mỗi lượt MỘT trọng tâm, 2-4 câu.

TRẢ VỀ DUY NHẤT MỘT JSON HỢP LỆ:
{
  "reasoning": "1-2 câu nội bộ: lập luận của họ đang tựa vào giả định nào, chỗ hổng ở đâu",
  "move": "refuse_and_redirect" | "probe_assumption" | "counterfactual" | "ledger_update" | "handoff_to_practice",
  "reply": "lời gửi học viên",
  "counterfactual": "điều kiện được đổi để thử độ vững — CHỈ điền khi move='counterfactual', còn lại chuỗi rỗng",
  "failure_condition": "một câu: lập luận hiện tại của họ hỏng trong điều kiện nào",
  "shifted": "điều gì trong lập luận của họ đã thay đổi so với lượt trước (chuỗi rỗng nếu chưa có gì đổi)",
  "unproven": "điều gì họ khẳng định nhưng chưa chứng minh được",
  "concept_gap": "khái niệm cần xem lại — CHỈ điền khi move='handoff_to_practice'",
  "practice_task": {"lab_ref": "vd: Task 1.1 · config/test_cases.json", "instruction": "việc tự làm, kiểm chứng được"},
  "reading_pointer": {"file": "vd: docs/CODELAB.md", "section": "vd: TASK 1.1 — ĐÁNH GIÁ 4 TIÊU CHÍ AGENTIC FIT", "why": "đọc để trả lời câu hỏi gì"},
  "criterion": "multi_step_reasoning | tool_interaction | dynamic_decision | long_horizon_goal",
  "stage": "1.1" | "1.2" | "2.1" | "2.2" | "3.1"
}
Khi move khác 'handoff_to_practice' thì để practice_task là {} và concept_gap là chuỗi rỗng.
Khi move='refuse_and_redirect' thì BẮT BUỘC điền reading_pointer; các move khác để {}."""

PAIRPAL_SOCRATIC_PROMPT = """Bạn là PairPal — một "bạn cùng bàn" ngây ngô trong Bài Lab 3 AI20k, đang học chung Task 1.1 Agentic Fit. Bạn hay hiểu lầm ngây thơ về AI/agent (ví dụ: "cứ là chatbot học vụ thì phải dùng ReAct Agent", "khai báo tool bằng văn bản cho nhanh") và nhờ người dùng GIẢI THÍCH cho bạn hiểu bản chất (hiệu ứng Protégé). Bạn KHÔNG đưa đáp án; bạn đặt câu hỏi ngô nghê hoặc nêu hiểu lầm để người dùng phải diễn đạt lại. Trả lời ngắn (2–3 câu), tiếng Việt, thân thiện."""


def socratic_reply(history: list[dict[str, Any]], round_title: str = "", persona: str = "mentor") -> dict[str, Any]:
    """Multi-turn Socratic tutor turn backed by a real LLM call (no offline mock).

    Mentor mode returns a structured JSON turn: an internal `reasoning` trace, a
    debating `reply` (devil's advocate) and — once the learner defends their
    reasoning — a harder `next_case` to auto-load as the next turn. PairPal is a
    plain naive-peer reply.

    history: list of {"role": "user"|"ai", "text": str} in chronological order.
    """
    api_key = os.getenv("OPENAI_API_KEY") or _fallback_api_key()
    if not api_key:
        return {"feedback": "", "error": "Chưa cấu hình OPENAI_API_KEY — không thể gọi LLM thật.", "model": "mock", "provider_status": "mock"}

    if persona == "pairpal":
        system_prompt = PAIRPAL_SOCRATIC_PROMPT
    else:
        system_prompt = MENTOR_SOCRATIC_PROMPT
        headings = _task_headings()
        if headings:
            system_prompt += (
                "\n\nHEADING CÓ THẬT TRONG docs/CODELAB.md "
                "(copy nguyên văn vào reading_pointer.section):\n" + headings
            )
    if round_title:
        system_prompt += f"\n\n[VÒNG HIỆN TẠI]: {round_title}"

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for m in (history or [])[-14:]:
        role = m.get("role")
        text = (m.get("text") or "").strip()
        if not text or role not in ("user", "ai"):
            continue
        messages.append({"role": "assistant" if role == "ai" else "user", "content": text})

    if len(messages) == 1:
        return {"feedback": "", "error": "empty_history", "model": "mock", "provider_status": "mock"}

    # PairPal: plain naive-peer reply via shared provider.
    if persona == "pairpal":
        from codebase.engine import get_provider
        provider = get_provider("openai", api_key=api_key, model="gpt-4o-mini")
        try:
            resp = provider.complete(messages, temperature=0.6)
            text = (resp.text or "").strip()
            if not text or text.startswith("[OpenAI Error"):
                return {"feedback": "", "error": text or "LLM trả về rỗng", "model": "mock", "provider_status": "error"}
            return {"feedback": text, "model": "gpt-4o-mini", "provider_status": "live"}
        except Exception as e:
            return {"feedback": "", "error": f"{type(e).__name__}: {str(e)[:200]}", "model": "mock", "provider_status": "error"}

    # Mentor: structured debate + reasoning + escalation via OpenAI JSON mode.
    import urllib.request

    payload = {
        "model": "gpt-4o-mini",
        "messages": messages,
        "temperature": 0.55,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        # Default TLS verification (no custom unverified context).
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        raw = data["choices"][0]["message"].get("content") or ""
    except Exception as e:
        return {"feedback": "", "error": f"{type(e).__name__}: {str(e)[:200]}", "model": "mock", "provider_status": "error"}

    # The debate turn carries a ledger, not a verdict: what shifted, what is
    # still unproven, the condition under which the argument fails, and — once
    # the gap is exposed — a piece of the lab the learner must code themselves.
    _ALLOWED_MOVES = (
        "refuse_and_redirect", "probe_assumption", "counterfactual",
        "ledger_update", "handoff_to_practice",
    )
    # A pointer may only name a file that actually exists in the lab repo, so a
    # refusal cannot send the learner to an invented path.
    _READABLE_LAB_FILES = frozenset(ALLOWLIST_PUBLIC_PATHS)
    _ALLOWED_CRITERIA = ("multi_step_reasoning", "tool_interaction", "dynamic_decision", "long_horizon_goal")
    _ALLOWED_STAGES = ("1.1", "1.2", "2.1", "2.2", "3.1")

    turn: dict[str, Any] = {
        "feedback": raw.strip(),
        "reasoning": "",
        "move": "probe_assumption",
        "counterfactual": "",
        "failure_condition": "",
        "shifted": "",
        "unproven": "",
        "concept_gap": "",
        "practice_task": {},
        "reading_pointer": {},
        "criterion": "",
        "stage": "1.1",
    }
    try:
        clean = raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw else raw
        parsed = json.loads(clean)

        def _str(key: str) -> str:
            return (parsed.get(key) or "").strip() if isinstance(parsed.get(key), str) else ""

        turn["feedback"] = _str("reply") or turn["feedback"]
        for key in ("reasoning", "counterfactual", "failure_condition", "shifted", "unproven", "concept_gap"):
            turn[key] = _str(key)

        move = _str("move")
        if move in _ALLOWED_MOVES:
            turn["move"] = move
        criterion = _str("criterion")
        if criterion in _ALLOWED_CRITERIA:
            turn["criterion"] = criterion
        stage = _str("stage")
        if stage in _ALLOWED_STAGES:
            turn["stage"] = stage

        pointer = parsed.get("reading_pointer")
        if isinstance(pointer, dict):
            pfile = pointer.get("file")
            if isinstance(pfile, str) and pfile.strip() in _READABLE_LAB_FILES:
                section = pointer.get("section")
                why = pointer.get("why")
                clean_file = pfile.strip()
                real_sections = _lab_sections().get(clean_file, [])
                clean_section = section.strip() if isinstance(section, str) else ""
                if clean_section and real_sections:
                    # Match tolerantly (the model drops the "2. " numbering),
                    # then store the canonical heading from the file itself.
                    def _norm(text: str) -> str:
                        body = text.split(".", 1)[-1] if text[:2].strip(".").isdigit() else text
                        return "".join(ch for ch in body.lower() if ch.isalnum())

                    want = _norm(clean_section)
                    clean_section = next(
                        (real for real in real_sections if _norm(real) == want), ""
                    )
                turn["reading_pointer"] = {
                    "file": clean_file,
                    "section": clean_section,
                    "why": why.strip() if isinstance(why, str) else "",
                }

        task = parsed.get("practice_task")
        if isinstance(task, dict):
            lab_ref = task.get("lab_ref")
            instruction = task.get("instruction")
            if isinstance(instruction, str) and instruction.strip():
                turn["practice_task"] = {
                    "lab_ref": lab_ref.strip() if isinstance(lab_ref, str) else "",
                    "instruction": instruction.strip(),
                }
    except Exception:
        pass  # non-JSON: fall back to raw text as the reply

    if not turn["feedback"]:
        return {"feedback": "", "error": "LLM trả về rỗng", "model": "mock", "provider_status": "error"}
    turn["model"] = "gpt-4o-mini"
    turn["provider_status"] = "live"
    return turn


DEBRIEF_SYSTEM_PROMPT = """Bạn tổng kết một buổi tranh luận Socratic của Bài Lab 3 AI20k.

Đọc toàn bộ hội thoại và chỉ ra chỗ học viên CÒN YẾU, tách làm hai trục khác nhau:
1. HIỂU KHÁI NIỆM — họ hiểu sai hoặc hiểu mơ hồ khái niệm nào (ví dụ: đánh đồng "cần dữ liệu
   ngoài" với "cần agent"; đánh đồng "nhiều bước xử lý" với "phải dùng LLM agent"; tưởng có
   vòng while là đã chứng minh multi-step chạy).
2. ÁP DỤNG THỰC TẾ — chỗ họ không chuyển được hiểu biết thành quyết định kỹ thuật kiểm chứng
   được (ví dụ: không nêu được dẫn chứng từ test case; không nói được sẽ đo bằng cách nào;
   khẳng định mà không có trace làm bằng chứng).

Sau đó giao MỘT phần của Lab họ NÊN TỰ CODE LẠI để tự kiểm chứng và cải thiện, bám đúng trình
tự Task 1.1 / 1.2 / 2.1 / 2.2 / 3.1 và các file thật của Lab (config/test_cases.json,
src/tools.py, src/app.py, docs/trace_waterfall.json, docs/trace_eval.md).

CẤM: chấm điểm đúng/sai, khen chung chung, viết code hộ, bịa nội dung file hay dòng code cụ thể.
Nếu hội thoại quá ngắn để kết luận, hãy nói thẳng là chưa đủ căn cứ và chỉ ra cần thêm gì.
Nhận xét phải trích được từ điều học viên đã thực sự nói trong hội thoại.

Tiếng Việt, mỗi mục 2-3 câu, thẳng thắn, không vòng vo.

TRẢ VỀ DUY NHẤT MỘT JSON HỢP LỆ:
{
  "concept_weakness": "chỗ yếu về hiểu khái niệm, dẫn lại điều họ đã nói",
  "application_weakness": "chỗ yếu về áp dụng thực tế, dẫn lại điều họ đã nói",
  "recode": {"lab_ref": "vd: Task 2.2 · src/app.py", "instruction": "việc tự code lại, kiểm chứng được"}
}"""


def debrief_reply(history: list[dict[str, Any]], stance: str = "", factors: list[str] | None = None) -> dict[str, Any]:
    """Close the session: name the weakness on both axes and hand back lab work.

    Real LLM only. On any provider/parse failure this reports the real status
    instead of returning a canned debrief dressed up as a model answer.
    """
    api_key = os.getenv("OPENAI_API_KEY") or _fallback_api_key()
    if not api_key:
        return {"error": "Chưa cấu hình OPENAI_API_KEY — không thể gọi LLM thật."}

    transcript: list[str] = []
    for m in (history or [])[-24:]:
        role = m.get("role")
        text = (m.get("text") or "").strip()
        if not text or role not in ("user", "ai"):
            continue
        transcript.append(("HỌC VIÊN: " if role == "user" else "COACH: ") + text)
    if not transcript:
        return {"error": "Chưa có hội thoại nào để tổng kết."}

    header = f"LẬP TRƯỜNG BAN ĐẦU: {stance or '(không ghi nhận)'}"
    if factors:
        header += "\nYẾU TỐ HỌ CHỌN: " + "; ".join(str(f) for f in factors)

    messages = [
        {"role": "system", "content": DEBRIEF_SYSTEM_PROMPT},
        {"role": "user", "content": header + "\n\nHỘI THOẠI:\n" + "\n".join(transcript)},
    ]

    import urllib.request

    payload = {
        "model": "gpt-4o-mini",
        "messages": messages,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        # Default TLS verification (no custom unverified context).
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        raw = data["choices"][0]["message"].get("content") or ""
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:200]}"}

    try:
        clean = raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw else raw
        parsed = json.loads(clean)
    except Exception:
        return {"error": "LLM trả về JSON không hợp lệ."}

    concept = parsed.get("concept_weakness")
    application = parsed.get("application_weakness")
    if not isinstance(concept, str) or not concept.strip():
        return {"error": "LLM không trả về concept_weakness."}

    recode_raw = parsed.get("recode")
    recode: dict[str, str] = {}
    if isinstance(recode_raw, dict):
        instruction = recode_raw.get("instruction")
        lab_ref = recode_raw.get("lab_ref")
        if isinstance(instruction, str) and instruction.strip():
            recode = {
                "lab_ref": lab_ref.strip() if isinstance(lab_ref, str) else "",
                "instruction": instruction.strip(),
            }

    return {
        "concept_weakness": concept.strip(),
        "application_weakness": application.strip() if isinstance(application, str) else "",
        "recode": recode,
        "model": "gpt-4o-mini",
        "provider_status": "live",
    }


def decision_evidence(student_msg: str, top_k: int = 3) -> tuple[list[dict[str, Any]], bool, str]:
    """Retrieve grounding evidence for a Mentor/PairPal chat turn.

    Same visibility filter as QA (publishable + bound + snapshot-current);
    unapproved data never reaches the response. Returns (evidence, False, "").
    """
    if not QA_CHUNKS_PATH.exists():
        return [], False, ""
    try:
        raw = search_sources(_get_qa_index(), "day03", student_msg, top_k=top_k * 3)
        visible = filter_visible_chunks(raw, _manifest_by_path(), snapshot_ok)[:top_k]
    except Exception:
        return [], False, ""
    return [_to_evidence(r) for r in visible], False, ""


# ---------------------------------------------------------------------------
# Gate 0 publish policy: which lab files may be served to browsers.
#
# A file is publishable ONLY if ALL hold (checked in this order, before any
# file bytes are read):
#   1. path normalizes to a safe relative path (no absolute/traversal/hidden),
#   2. path is not on the absolute deny list (secrets/logs/keys/chatlogs),
#   3. path is in the manually confirmed public allowlist below,
#   4. path has an entry in the ingested manifest,
#   5. resolved path stays inside PUBLIC_LAB_DIR, is not a symlink, is a file,
#   6. SHA-256 of current bytes matches the manifest (else stale -> re-ingest).
# ---------------------------------------------------------------------------
PUBLIC_LAB_DIR = PROJECT_ROOT / "data" / "K4-Day03-Lab"

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

_MANIFEST_CACHE: dict[str, Any] | None = None
_CHUNKS_CACHE: list[dict[str, Any]] | None = None


def _reset_publish_caches() -> None:
    global _MANIFEST_CACHE, _CHUNKS_CACHE, _QA_INDEX_CACHE
    _MANIFEST_CACHE = None
    _CHUNKS_CACHE = None
    _QA_INDEX_CACHE = None


def _manifest_by_path() -> dict[str, dict[str, Any]]:
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is None:
        try:
            data = json.loads(QA_MANIFEST_PATH.read_text(encoding="utf-8"))
            _MANIFEST_CACHE = {
                f.get("path"): f for f in data.get("files", []) if f.get("path")
            }
        except Exception:
            _MANIFEST_CACHE = {}
    return _MANIFEST_CACHE


def _chunks_all() -> list[dict[str, Any]]:
    global _CHUNKS_CACHE
    if _CHUNKS_CACHE is None:
        try:
            _CHUNKS_CACHE = load_chunk_index(QA_CHUNKS_PATH)
        except Exception:
            _CHUNKS_CACHE = []
    return _CHUNKS_CACHE


def _load_verified(rel_path: str) -> tuple[bytes | None, str]:
    """Permission checks first, then read + SHA bind against the manifest.

    Returns (content, "") on success, else (None, generic reason code).
    Shared snapshot verifier for /api/file, /api/chunks and all retrieval:
    when the on-disk source drifts from the manifest, every path refuses
    (stale -> re-ingest) instead of serving mixed snapshots.
    """
    rel = normalize_rel_path(rel_path)
    if rel is None:
        return None, "invalid_path"
    manifest = _manifest_by_path()
    ok, reason = is_publishable(rel, manifest)
    if not ok:
        return None, reason
    try:
        root = PUBLIC_LAB_DIR.resolve()
        candidate = PUBLIC_LAB_DIR / rel
        if candidate.is_symlink():
            return None, "not_found"
        target = candidate.resolve()
        target.relative_to(root)
        if not target.is_file():
            return None, "not_found"
    except (ValueError, RuntimeError, OSError):
        return None, "not_found"
    try:
        content = target.read_bytes()
    except OSError:
        return None, "not_found"
    import hashlib

    if hashlib.sha256(content).hexdigest() != manifest[rel].get("sha256", ""):
        return None, "stale"
    return content, ""


def snapshot_ok(rel_path: str) -> bool:
    """Live check: current on-disk file still matches the manifest snapshot."""
    content, _ = _load_verified(rel_path)
    return content is not None


def resolve_publishable_file(rel_path: str) -> tuple[Path | None, bytes, str]:
    content, reason = _load_verified(rel_path)
    if reason:
        return None, b"", reason
    rel = normalize_rel_path(rel_path) or ""
    return PUBLIC_LAB_DIR / rel, content, ""


def _request_is_local(handler: Any) -> bool:
    """Loopback Host (+ Origin/Referer when present) check for /api/* routes."""
    import urllib.parse

    host = (handler.headers.get("Host", "") or "").split(":")[0].strip().lower().strip("[]")
    if host not in LOCAL_HOSTS:
        return False
    for header in ("Origin", "Referer"):
        origin = handler.headers.get(header)
        if origin:
            try:
                ohost = (urllib.parse.urlparse(origin).hostname or "").lower()
            except Exception:
                return False
            if ohost not in LOCAL_HOSTS:
                return False
    return True


# ---------------------------------------------------------------------------
# Web Server
# ---------------------------------------------------------------------------
class PrototypeWebHandler(BaseHTTPRequestHandler):
    engine = CentralDecisionEngine()
    ui_path = CODEBASE_DIR / "ui.html"

    def do_GET(self):
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(self.path)

            if parsed.path.startswith("/api/") and not _request_is_local(self):
                self.send_error(403, "Forbidden")
                return

            if parsed.path == "/api/manifest":
                try:
                    manifest_data = json.loads(QA_MANIFEST_PATH.read_text(encoding="utf-8"))
                except Exception:
                    self.send_error(404, "Not found")
                    return
                # Same publish policy as /api/file: only allowlisted files,
                # no skipped-file details (may name secret-bearing files).
                manifest_index = {
                    f.get("path"): f
                    for f in manifest_data.get("files", [])
                    if f.get("path")
                }
                filtered_files = []
                for f in manifest_data.get("files", []):
                    if f.get("size_bytes", 0) <= 0:
                        continue
                    p = f.get("path", "")
                    ok, _ = is_publishable(p, manifest_index)
                    if not ok:
                        continue
                    cat = "docs"
                    if p.startswith("src/"):
                        cat = "code"
                    elif p.startswith("tests/") or p.startswith("config/") or p.endswith(".json"):
                        cat = "tests"
                    filtered_files.append({
                        "path": p,
                        "sha256": f.get("sha256", ""),
                        "size_bytes": f.get("size_bytes", 0),
                        "total_lines": f.get("total_lines", 0),
                        "source_kind": f.get("source_kind", ""),
                        "symbols": f.get("symbols", []),
                        "symbols_count": f.get("symbols_count", 0),
                        "category": cat,
                    })

                body = json.dumps({
                    "lab_id": manifest_data.get("lab_id", ""),
                    "source_manifest_sha256": manifest_data.get("source_manifest_sha256", ""),
                    "generated_at": manifest_data.get("generated_at", ""),
                    "files_count": len(filtered_files),
                    "files": filtered_files,
                }, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/file":
                query = urllib.parse.parse_qs(parsed.query)
                file_path = query.get("path", [None])[0]
                if not file_path:
                    self.send_error(400, "Bad request")
                    return

                _, content_bytes, reason = resolve_publishable_file(file_path)
                if reason == "stale":
                    self.send_error(409, "Source changed")
                    return
                if reason:
                    self.send_error(404, "Not found")
                    return
                rel = normalize_rel_path(file_path) or ""
                try:
                    content = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    self.send_error(404, "Not found")
                    return
                import hashlib
                file_hash = hashlib.sha256(content_bytes).hexdigest()
                lines = content.splitlines()

                symbols = []
                if rel.endswith(".py"):
                    try:
                        import ast
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                symbols.append({
                                    "name": node.name,
                                    "kind": "function",
                                    "line": node.lineno,
                                    "end_line": getattr(node, "end_lineno", node.lineno)
                                })
                            elif isinstance(node, ast.ClassDef):
                                symbols.append({
                                    "name": node.name,
                                    "kind": "class",
                                    "line": node.lineno,
                                    "end_line": getattr(node, "end_lineno", node.lineno)
                                })
                    except Exception:
                        pass

                payload = {
                    "path": rel,
                    "content": content,
                    "total_lines": len(lines),
                    "sha256": file_hash,
                    "symbols": symbols
                }
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/chunks":
                # Same publish policy as /api/file: a chunk is served only if
                # its file is publishable AND the chunk is bound to the current
                # manifest SHA (stale/unbound chunks are dropped).
                query = urllib.parse.parse_qs(parsed.query)
                chunk_id = query.get("chunk_id", [None])[0]
                file_path = query.get("path", [None])[0]
                if not chunk_id and not file_path:
                    self.send_error(400, "Bad request")
                    return
                norm_path = None
                if file_path:
                    norm_path = normalize_rel_path(file_path)
                    if norm_path is None:
                        self.send_error(400, "Bad request")
                        return

                manifest_index = _manifest_by_path()
                candidates = []
                for item in _chunks_all():
                    if chunk_id and item.get("chunk_id") != chunk_id:
                        continue
                    if norm_path and item.get("path") != norm_path:
                        continue
                    if not chunk_id and not norm_path:
                        continue
                    candidates.append(item)
                    if len(candidates) >= 300:
                        break
                # Same snapshot guarantee as /api/file: stale or unapproved
                # chunks are dropped, never served.
                results = filter_visible_chunks(candidates, manifest_index, snapshot_ok)[:100]

                payload = results[0] if (chunk_id and results) else results
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path in ("/", "/index.html", "/ui.html", "/ui_v1.html"):
                target = CODEBASE_DIR / "ui.html"
                if not target.exists():
                    self.send_error(404, "Not found")
                    return
                body = target.read_text(encoding="utf-8").encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/provider-status":
                api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or _fallback_api_key()
                has_openai = bool(os.getenv("OPENAI_API_KEY") or (api_key and api_key.startswith("sk-")))
                has_gemini = bool(os.getenv("GEMINI_API_KEY") or (api_key and api_key.startswith("AIza")))
                status = "live_openai" if has_openai else ("live_gemini" if has_gemini else "mock")
                body = json.dumps({"status": status, "openai": has_openai, "gemini": has_gemini}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/labs":
                body = json.dumps({"labs": labs.list_labs()}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/qa":
                # Q&A moved to POST /api/qa (a GET cannot reliably carry a JSON body).
                self.send_error(405, "Use POST /api/qa")
                return

            self.send_error(404)
        except Exception:
            import traceback
            traceback.print_exc()
            self.send_error(500, "Internal error")

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        raw_bytes = self.rfile.read(length) if length else b""
        try:
            body_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            body_text = raw_bytes.decode("latin1", errors="replace")
        return json.loads(body_text) if body_text else {}

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            if self.path.startswith("/api/") and not _request_is_local(self):
                self.send_error(403, "Forbidden")
                return
            if self.path == "/api/qa":
                payload = self._read_json_body()
                query = (payload.get("query", "") or "").strip()
                if not query:
                    self.send_error(400, "Bad request")
                    return
                try:
                    top_k = int(payload.get("top_k", 5) or 5)
                except (TypeError, ValueError):
                    top_k = 5
                self._send_json(answer_qa(query, top_k=max(1, min(top_k, 10))))
                return

            if self.path == "/api/socratic":
                payload = self._read_json_body()
                history = payload.get("history", []) or []
                round_title = (payload.get("round_title", "") or "").strip()
                persona = (payload.get("persona", "mentor") or "mentor").strip()
                self._send_json(socratic_reply(history, round_title=round_title, persona=persona))
                return

            if self.path == "/api/debrief":
                payload = self._read_json_body()
                history = payload.get("history", []) or []
                stance = (payload.get("stance", "") or "").strip()
                factors_raw = payload.get("factors", []) or []
                factors = [str(f) for f in factors_raw if isinstance(f, str)][:2]
                self._send_json(debrief_reply(history, stance=stance, factors=factors))
                return

            if self.path == "/api/decision":
                payload = self._read_json_body()
                msg = payload.get("message", "")
                stage = payload.get("stage", "orientation")

                outcome, log_entry = self.engine.decide(student_input=msg, current_stage=stage)

                # Grounding: retrieve real chunks for this turn and check whether
                # the heuristic citation names a file actually in the index.
                evidence, _, _ = decision_evidence(msg)
                citation_verified = any(
                    ev.get("path") and ev["path"] in (outcome.citation or "")
                    for ev in evidence
                )

                resp_data = {
                    "action_type": outcome.action_type,
                    "feedback": outcome.feedback,
                    "citation": outcome.citation,
                    "citation_verified": citation_verified,
                    "evidence": evidence,
                    "simulated_consequence": outcome.simulated_consequence,
                    "options": outcome.options,
                    "risk_level": outcome.risk_level,
                    "latency_ms": log_entry.latency_ms,
                    "model": log_entry.model,
                }

                self._send_json(resp_data)
                return

            if self.path == "/api/session":
                payload = self._read_json_body()
                lab_id = (payload.get("lab_id") or "").strip()
                session = create_session()
                if lab_id:
                    bundle = labs.get_lab_bundle(lab_id)
                    if bundle:
                        session.lab_id = lab_id
                        session.current_checkpoint = bundle.checkpoints[0].checkpoint_id if bundle.checkpoints else None
                self._send_json({
                    "session_id": session.session_id,
                    "lab_id": session.lab_id,
                    "current_checkpoint": session.current_checkpoint,
                })
                return

            if self.path == "/api/labs":
                self._send_json({"labs": labs.list_labs()})
                return

            if self.path == "/api/session/checkpoint":
                payload = self._read_json_body()
                session_id = payload.get("session_id")
                checkpoint_id = payload.get("checkpoint_id")
                session = get_session(session_id)
                if not session or not session.lab_id:
                    self.send_error(404, "Session not found")
                    return
                bundle = labs.get_lab_bundle(session.lab_id)
                if not bundle:
                    self.send_error(404, "Lab not found")
                    return
                cp = bundle.checkpoint(checkpoint_id) if checkpoint_id else bundle.checkpoint(session.current_checkpoint or "")
                if not cp:
                    self.send_error(404, "Checkpoint not found")
                    return
                evidence = []
                for eid in cp.evidence_ids:
                    ec = bundle.evidence(eid)
                    if ec:
                        evidence.append({
                            "evidence_id": ec.evidence_id,
                            "title": ec.title,
                            "source_path": ec.source_path,
                            "start_line": ec.start_line,
                            "end_line": ec.end_line,
                            "source_kind": ec.source_kind,
                            "label": ec.label,
                        })
                self._send_json({
                    "checkpoint_id": cp.checkpoint_id,
                    "title": cp.title,
                    "briefing": cp.briefing,
                    "objective": cp.objective,
                    "scenario": cp.scenario,
                    "evidence_ids": cp.evidence_ids,
                    "evidence_cards": evidence,
                    "quiz_ids": cp.quiz_ids,
                    "hint_level": session.hint_level,
                    "viewed_evidence_ids": session.viewed_evidence_ids,
                    "hypothesis_versions": session.hypothesis_versions,
                })
                return

            if self.path == "/api/session/next-checkpoint":
                payload = self._read_json_body()
                session_id = payload.get("session_id")
                session = get_session(session_id)
                if not session or not session.lab_id:
                    self.send_error(404, "Session not found")
                    return
                bundle = labs.get_lab_bundle(session.lab_id)
                if not bundle:
                    self.send_error(404, "Lab not found")
                    return
                idx = next(
                    (i for i, c in enumerate(bundle.checkpoints) if c.checkpoint_id == session.current_checkpoint),
                    -1,
                )
                if idx + 1 < len(bundle.checkpoints):
                    session.current_checkpoint = bundle.checkpoints[idx + 1].checkpoint_id
                    session.hint_level = 0
                    update_session(session_id, current_checkpoint=session.current_checkpoint, hint_level=session.hint_level)
                    self._send_json({"checkpoint_id": session.current_checkpoint, "has_next": True})
                else:
                    self._send_json({"checkpoint_id": session.current_checkpoint, "has_next": False})
                return

            if self.path == "/api/session/tip":
                payload = self._read_json_body()
                session_id = payload.get("session_id")
                session = get_session(session_id)
                if not session or not session.lab_id:
                    self.send_error(404, "Session not found")
                    return
                checkpoint_id = payload.get("checkpoint_id", session.current_checkpoint or "")
                bundle = labs.get_lab_bundle(session.lab_id)
                if not bundle:
                    self.send_error(404, "Lab not found")
                    return
                cp = bundle.checkpoint(checkpoint_id)
                if not cp:
                    self.send_error(404, "Checkpoint not found")
                    return
                available = [
                    t for t in bundle.tips_for(cp.checkpoint_id)
                    if t.tip_id not in session.viewed_tip_ids
                ]
                shown_before = [
                    t for t in bundle.tip_cards
                    if t.tip_id in session.viewed_tip_ids and t.checkpoint_id == cp.checkpoint_id
                ]
                import random
                rng = random.Random(len(session.viewed_tip_ids))
                if available:
                    tip = rng.choice(available)
                elif shown_before:
                    tip = rng.choice(shown_before)
                else:
                    self._send_json({"tip": None})
                    return
                session.viewed_tip_ids.append(tip.tip_id)
                update_session(session_id, viewed_tip_ids=session.viewed_tip_ids)
                self._send_json({
                    "tip_id": tip.tip_id,
                    "content": tip.content,
                    "source": tip.source,
                    "tags": tip.tags,
                    "spoiler_for": tip.spoiler_for,
                })
                return

            if self.path == "/api/session/evidence":
                payload = self._read_json_body()
                session_id = payload.get("session_id")
                evidence_id = payload.get("evidence_id")
                session = get_session(session_id)
                if not session:
                    self.send_error(404, "Session not found")
                    return
                if evidence_id not in session.viewed_evidence_ids:
                    session.viewed_evidence_ids.append(evidence_id)
                    update_session(session_id, viewed_evidence_ids=session.viewed_evidence_ids)
                self._send_json({"ok": True, "viewed_evidence_ids": session.viewed_evidence_ids})
                return

            if self.path == "/api/session/hypothesis":
                payload = self._read_json_body()
                session_id = payload.get("session_id")
                hypothesis = payload.get("hypothesis", "")
                session = get_session(session_id)
                if not session:
                    self.send_error(404, "Session not found")
                    return
                session.hypothesis_versions.append(hypothesis)
                update_session(session_id, hypothesis_versions=session.hypothesis_versions)
                self._send_json({"ok": True, "version": len(session.hypothesis_versions)})
                return

            if self.path == "/api/session/coach":
                payload = self._read_json_body()
                session_id = payload.get("session_id")
                hint_level = payload.get("hint_level", 0)
                session = get_session(session_id)
                if not session:
                    self.send_error(404, "Session not found")
                    return
                if not session.hypothesis_versions:
                    self._send_json({"error": "Vui lòng nhập nhận định trước khi xin phản hồi AI"})
                    return
                client = _get_coach_client()
                if not client:
                    self._send_json({"error": "API key chưa cấu hình. Không thể gọi AI Coach."})
                    return
                try:
                    evidence = _load_bundle_evidence()
                    feedback = get_coach_feedback(
                        session=session,
                        bundle_evidence=evidence,
                        objective=LAB3_OBJECTIVE,
                        hint_level=HintLevel(hint_level),
                        client=client
                    )
                    self._send_json(feedback.model_dump(mode='json'))
                except Exception as e:
                    self._send_json({"error": f"Coach error: {e}"})
                return

            if self.path == "/api/session/quiz":
                payload = self._read_json_body()
                session_id = payload.get("session_id")
                question_id = payload.get("question_id")
                selected = payload.get("selected", [])
                session = get_session(session_id)
                if not session:
                    self.send_error(404, "Session not found")
                    return
                question = get_question(question_id)
                if not question:
                    self.send_error(404, "Question not found")
                    return
                attempt = record_attempt(session, question, selected)
                update_session(session_id, quiz_attempts=session.quiz_attempts)
                result = {
                    "question_id": question_id,
                    "correct": attempt.correct,
                    "attempt_number": attempt.attempt_number,
                    "post_reveal": attempt.post_reveal,
                    "explanation": question.explanation,
                }
                self._send_json(result)
                return

            if self.path == "/api/session/quiz/summary":
                payload = self._read_json_body()
                session_id = payload.get("session_id")
                session = get_session(session_id)
                if not session:
                    self.send_error(404, "Session not found")
                    return
                self._send_json(get_quiz_summary(session))
                return

            if self.path == "/api/session/self-report":
                payload = self._read_json_body()
                session_id = payload.get("session_id")
                value = payload.get("value")
                session = get_session(session_id)
                if not session:
                    self.send_error(404, "Session not found")
                    return
                if value not in ("completed", "in_progress", "not_started", "prefer_not_to_say", None):
                    self.send_error(400, "Invalid value")
                    return
                session.self_report = value
                session.self_report_at = __import__("datetime").datetime.utcnow()
                update_session(session_id, self_report=value, self_report_at=session.self_report_at)
                self._send_json({"ok": True, "self_report": value})
                return

            self.send_error(404)
        except Exception:
            import traceback
            traceback.print_exc()
            self.send_error(500, "Internal error")

    def log_message(self, format: str, *args: Any):
        try:
            msg = format % args
        except Exception:
            msg = " ".join(str(a) for a in args) if args else format
        sys.stderr.write(f"[HTTP] {self.address_string()} - {msg}\n")


def run_web(port: int = 3000):
    # Gate 0: loopback only. No public-bind option in this task; loopback is
    # NOT a substitute for authentication when deploying to a network.
    server = ThreadingHTTPServer(("127.0.0.1", port), PrototypeWebHandler)
    print("\n" + "=" * 70)
    print(f"Lunch Tutorial Decision Core Prototype Web UI đang chạy tại:")
    print(f"👉 http://127.0.0.1:{port}")
    print("=" * 70)
    print("Sẵn sàng cho thao tác trực tiếp và quay video màn hình 30 giây.")
    print("Bấm Ctrl+C để dừng server.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
        print("\nĐã dừng server.")


# ---------------------------------------------------------------------------
# CLI Runner
# ---------------------------------------------------------------------------
def run_cli():
    engine = CentralDecisionEngine()
    print("\n" + "=" * 70)
    print("  Lunch Tutorial Central Decision Core — CLI Runner (CP3)")
    print("=" * 70)
    print("Gõ câu hỏi/hành động của học viên để AI phân tích và đưa ra quyết định.")
    print("Gõ 'exit' hoặc 'quit' để thoát.\n")

    while True:
        try:
            inp = input("Học viên > ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not inp or inp.lower() in ("exit", "quit"):
            break

        outcome, log_entry = engine.decide(inp)
        print(f"\n[AI QUYẾT ĐỊNH: {outcome.action_type}] (Latency: {log_entry.latency_ms}ms · Model: {log_entry.model})")
        print(f"💬 Phản hồi: {outcome.feedback}")
        if outcome.citation:
            print(f"📚 Căn cứ trích dẫn: {outcome.citation}")
        if outcome.simulated_consequence:
            print(f"⚠️ Dự báo hệ quả: {outcome.simulated_consequence}")
        print("👉 Lựa chọn tiếp theo:")
        for opt in outcome.options:
            status_mark = "✓" if opt.get("correct") else "✗"
            print(f"   [{opt['id']}] {opt['label']} ({status_mark})")
        print(f"📝 Trace đã lưu vào: codebase/logs/inference_traces.jsonl\n" + "-" * 70)


def main():
    parser = argparse.ArgumentParser(description="LabPath Central Decision Core Prototype (CP3)")
    parser.add_argument("--web", action="store_true", help="Start Web UI server (default: port 3000)")
    parser.add_argument("--port", type=int, default=3000, help="Web server port")
    parser.add_argument("--query", type=str, default="", help="Single query test")
    args = parser.parse_args()

    if args.web:
        run_web(port=args.port)
    elif args.query:
        engine = CentralDecisionEngine()
        outcome, log = engine.decide(args.query)
        print(json.dumps({
            "action_type": outcome.action_type,
            "feedback": outcome.feedback,
            "citation": outcome.citation,
            "consequence": outcome.simulated_consequence,
            "options": outcome.options,
            "latency_ms": log.latency_ms,
            "model": log.model,
        }, ensure_ascii=False, indent=2))
    else:
        run_cli()


if __name__ == "__main__":
    main()

"""
LunchTutor — Central Decision Core (CP3 AI Prototype)

This module implements the primary AI decision engine:
1. Receives student input, lab context, and current stage.
2. Invokes real LLM API (OpenAI or Gemini) or high-fidelity offline heuristic solver.
3. Classifies student intent & risk (Direct Answer Request, Premature Action, Factual Inquiry, Ambiguity, Out of Scope).
4. Predicts/simulates consequences and formulates next pedagogical guidance (without solving it for the student).
5. Logs every inference (input prompt, raw response, latency, decision outcome) for technical audit.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from codebase.tools import load_env_api_key
except ImportError:  # pragma: no cover
    from tools import load_env_api_key

# ---------------------------------------------------------------------------
# Directories & Logging
# ---------------------------------------------------------------------------
CODEBASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CODEBASE_DIR.parent
LOGS_DIR = CODEBASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
TRACE_LOG_FILE = LOGS_DIR / "inference_traces.jsonl"


# ---------------------------------------------------------------------------
# Decision Data Structures
# ---------------------------------------------------------------------------
@dataclass
class DecisionOutcome:
    action_type: str  # REFUSE_AND_PROBE, WARN_PREMATURE, CLARIFY_AMBIGUOUS, CITE_GROUNDED, EVALUATE_DECISION
    feedback: str
    citation: str = ""
    simulated_consequence: str = ""
    options: list[dict[str, Any]] = field(default_factory=list)
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH


@dataclass
class InferenceLog:
    timestamp: str
    model: str
    latency_ms: float
    input_prompt: str
    raw_response: str
    decision: dict[str, Any]
    status: str = "SUCCESS"
    provider_attempted: str = ""
    provider_actual: str = ""
    fallback_reason: str = ""


# ---------------------------------------------------------------------------
# System Prompt for Decision Core
# ---------------------------------------------------------------------------
DECISION_CORE_SYSTEM_PROMPT = """Bạn là Bộ Não Quyết Định Trung Tâm của hệ thống LabPath / LunchTutor (AI Socratic Lab Tutor).
Nhiệm vụ của bạn là hướng dẫn học viên thực hành bài lab mà TUYỆT ĐỐI KHÔNG làm hộ, không cho đáp án trực tiếp, không sinh full code thay thế.

QUY TẮC BẮT BUỘC:
1. Nếu học viên xin code trực tiếp ("cho đáp án", "gửi full code", "giải hộ"):
   - TỪ CHỐI cung cấp code/đáp án hoàn chỉnh.
   - Giải thích lý do sư phạm (mục tiêu tự rèn luyện).
   - Đặt 1 câu hỏi Socratic gợi mở hướng tiếp cận và đưa ra 3 hành động gợi ý (A, B, C).
2. Nếu học viên hành động vội vàng ("bắt đầu code luôn", bỏ qua checkpoint/setup):
   - CẢNH BÁO hệ quả: code sẽ lỗi hoặc vi phạm quy chế lab nếu chưa cài đặt môi trường và đọc tài liệu.
   - Gợi ý kiểm tra checkpoint trước.
3. Nếu câu hỏi mơ hồ hoặc thiếu thông tin:
   - ĐẶT CÂU HỎI LÀM RÕ (Clarification) thay vì đoán mò.
4. Nếu câu hỏi về kiến thức / quy chế:
   - TRÍCH DẪN NGUỒN SỰ THẬT (ví dụ slide bài giảng [T01-042], quy chế đào tạo, hoặc file README/template).
5. Luôn trả lời dưới định dạng JSON duy nhất:
{
  "action_type": "REFUSE_AND_PROBE" | "WARN_PREMATURE" | "CLARIFY_AMBIGUOUS" | "CITE_GROUNDED" | "EVALUATE_DECISION",
  "risk_level": "LOW" | "MEDIUM" | "HIGH",
  "feedback": "Phản hồi sư phạm gửi học viên",
  "citation": "Nguồn tham chiếu [Txx-NNN] hoặc file bài lab",
  "simulated_consequence": "Hệ quả mô phỏng nếu học viên thực hiện hành động",
  "options": [
    {"id": "A", "label": "Hành động đúng chuẩn", "correct": true},
    {"id": "B", "label": "Hành động đốt cháy giai đoạn", "correct": false},
    {"id": "C", "label": "Hành động sửa sai không có căn cứ", "correct": false}
  ]
}
"""






class CentralDecisionEngine:
    def __init__(self, model: str = "gpt-4o-mini", api_key: str = ""):
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or load_env_api_key() or ""
        self.provider_type = self._detect_provider()

    def _detect_provider(self) -> str:
        if os.getenv("OPENAI_API_KEY") or (self.api_key and self.api_key.startswith("sk-")):
            return "openai"
        if os.getenv("GEMINI_API_KEY") or (self.api_key and "AIza" in self.api_key):
            return "gemini"
        return "heuristic_offline"

    def decide(self, student_input: str, current_stage: str = "orientation", lab_context: str = "") -> tuple[DecisionOutcome, InferenceLog]:
        """Execute decision turn: formulate prompt -> call LLM / heuristic -> log -> parse."""
        prompt = f"""[TRẠNG THÁI LAB HIỆN TẠI]: Chặng '{current_stage}'.
[NGỮ CẢNH TÀI LIỆU/CODE]: {lab_context or "Lab 01-03 AI20k, file template.py, slide bài giảng VLearn."}
[HÀNH ĐỘNG / YÊU CẦU CỦA HỌC VIÊN]:
\"\"\"{student_input}\"\"\"

Hãy đưa ra quyết định sư phạm theo định dạng JSON quy định."""

        t0 = time.perf_counter()
        provider_attempted = self.provider_type
        provider_actual = "heuristic-deterministic-engine"
        status = "heuristic_offline"
        fallback_reason = ""
        raw_response = ""

        if self.provider_type == "openai":
            raw_response, ok, reason = self._call_openai(prompt)
            provider_actual = self.model if ok else "heuristic-deterministic-engine"
            status = "live_success" if ok else "live_error_fallback"
            fallback_reason = "" if ok else reason
        elif self.provider_type == "gemini":
            raw_response, ok, reason = self._call_gemini(prompt)
            provider_actual = "gemini-2.5-flash" if ok else "heuristic-deterministic-engine"
            status = "live_success" if ok else "live_error_fallback"
            fallback_reason = "" if ok else reason
        else:
            raw_response = self._solve_heuristic(student_input, current_stage)

        latency_ms = (time.perf_counter() - t0) * 1000

        # Parse outcome
        outcome = self._parse_outcome(raw_response, student_input)

        # Record inference log (server-side audit only; never sent to clients).
        log_entry = InferenceLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            model=provider_actual,
            provider_attempted=provider_attempted,
            provider_actual=provider_actual,
            status=status,
            fallback_reason=fallback_reason,
            latency_ms=round(latency_ms, 2),
            input_prompt=prompt,
            raw_response=raw_response,
            decision=asdict(outcome),
        )
        self._append_trace_log(log_entry)

        return outcome, log_entry

    def _call_openai(self, prompt: str) -> tuple[str, bool, str]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": DECISION_CORE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            # Default TLS verification (no custom unverified context).
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"], True, ""
        except Exception as err:
            reason = f"OpenAI error: {type(err).__name__}: {str(err)[:200]}"
            return self._solve_heuristic(prompt, "heuristic-fallback"), False, reason

    def _call_gemini(self, prompt: str) -> tuple[str, bool, str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"{DECISION_CORE_SYSTEM_PROMPT}\n\n{prompt}"}]}
            ],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        try:
            # Default TLS verification (no custom unverified context).
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"], True, ""
        except Exception as err:
            reason = f"Gemini error: {type(err).__name__}: {str(err)[:200]}"
            return self._solve_heuristic(prompt, "heuristic-fallback"), False, reason

    def _solve_heuristic(self, student_input: str, stage: str) -> str:
        """High-fidelity heuristic decision solver reflecting exact 4-class taxonomy."""
        inp = student_input.lower().strip()

        # Class 3: Out of Scope / Direct Answer Requests / Prompt Injection / Exam leaks
        if any(w in inp for w in (
            "đáp án", "full code", "code luôn đi", "cho code", "giải bài", "giải hộ",
            "yolo11n", "colab", "bỏ qua mọi hướng dẫn", "override", "viết code hoàn thiện",
            "đề thi", "bài kiểm tra cuối khoá", "viết lại code cho tôi", "sửa hộ"
        )):
            return json.dumps({
                "action_type": "REFUSE_AND_PROBE",
                "risk_level": "HIGH",
                "feedback": "Hệ thống không cung cấp đáp án hoặc code hoàn chỉnh trực tiếp. Để hiểu bản chất, bạn cần xác định yêu cầu và tự triển khai từng bước.",
                "citation": "VLearn Lab Policy §3 · Trợ lý không giải hộ bài tập",
                "simulated_consequence": "Nếu nhận code có sẵn, học viên sẽ không thể giải thích nguyên lý khi thuyết trình hoặc gặp lỗi tương tự ở bài lab sau.",
                "options": [
                    {"id": "A", "label": "Đọc LAB-GUIDE.md để xác định mục tiêu của Task 1 trước", "correct": True},
                    {"id": "B", "label": "Nhờ AI bên ngoài sinh code rồi dán vào", "correct": False},
                    {"id": "C", "label": "Bỏ qua task và chuyển sang bài tiếp theo", "correct": False},
                ],
            }, ensure_ascii=False)

        # Day 03: ReAct Loop & Truncated Loop & Tool Schema & Guardrail
        if any(w in inp for w in (
            "truncated", "ngắt luồng", "ngắt sớm", "vòng lặp react", "react loop",
            "observation", "thought", "break", "infinite loop"
        )):
            return json.dumps({
                "action_type": "CITE_GROUNDED",
                "risk_level": "LOW",
                "feedback": "Vòng lặp ReAct trong src/app.py xử lý Thought -> Action -> Observation. Cần nạp Observation vào messages và tiếp tục vòng lặp để gọi tiếp Tool 2, tránh bẫy Truncated Loop do đặt lệnh break sai chỗ.",
                "citation": "src/app.py:36-75 · ReAct Loop Execution Layer",
                "simulated_consequence": "Nếu lệnh break ngắt sớm sau Tool 1, Agent sẽ dừng luồng và không thể thực hiện các bài toán suy luận đa bước (như TC03, TC04).",
                "options": [
                    {"id": "A", "label": "Nạp Observation vào messages và duy trì while step < MAX_STEPS", "correct": True},
                    {"id": "B", "label": "Đặt break ngay sau khi gọi Tool lần đầu", "correct": False},
                    {"id": "C", "label": "Bỏ hẳn điều kiện dừng MAX_STEPS", "correct": False},
                ],
            }, ensure_ascii=False)

        if any(w in inp for w in ("schema", "required", "tool", "dispatch", "json schema", "properties")):
            return json.dumps({
                "action_type": "CITE_GROUNDED",
                "risk_level": "LOW",
                "feedback": "Tool Schema trong src/tools.py phải tuân thủ chuẩn JSON Schema với type: 'object', properties chi tiết và mảng required bắt buộc để LLM không sinh arguments rỗng.",
                "citation": "src/tools.py:1-40 · Tool Schemas & Dispatcher",
                "simulated_consequence": "Thiếu mảng required sẽ khiến LLM sinh thiếu tham số khi gọi schedule_appointment, làm hàm dispatch văng lỗi runtime.",
                "options": [
                    {"id": "A", "label": "Khai báo đầy đủ mảng required: ['student_id', 'advisor_id', 'datetime']", "correct": True},
                    {"id": "B", "label": "Bỏ qua trường required để cho gọn", "correct": False},
                    {"id": "C", "label": "Chỉ dùng chuỗi mô tả tự do không theo schema", "correct": False},
                ],
            }, ensure_ascii=False)

        if any(w in inp for w in ("guardrail", "bảo mật", "sv9999999", "khác", "tiết lộ", "học vụ", "tc05")):
            return json.dumps({
                "action_type": "WARN_PREMATURE",
                "risk_level": "MEDIUM",
                "feedback": "Theo quy chế bảo vệ dữ liệu học viên (TC05), lớp Guardrail phải kiểm tra và từ chối truy vấn hồ sơ hoặc đặt lịch thay sinh viên khác trước khi gọi Tool.",
                "citation": "src/guardrail_agent.py & config/test_cases.json TC05",
                "simulated_consequence": "Nếu bỏ qua Guardrail, Agent sẽ làm lộ thông tin cá nhân của sinh viên khác, bị đánh trượt tiêu chí an toàn trong Rubric.",
                "options": [
                    {"id": "A", "label": "Chặn qua Guardrail trước khi dispatch tool call", "correct": True},
                    {"id": "B", "label": "Thực thi luôn không cần kiểm tra quyền sinh viên", "correct": False},
                    {"id": "C", "label": "Chỉ cảnh báo sau khi đã lấy được dữ liệu", "correct": False},
                ],
            }, ensure_ascii=False)

        if any(w in inp for w in ("trace", "waterfall", "báo cáo", "nộp bài", "rubric")):
            return json.dumps({
                "action_type": "CITE_GROUNDED",
                "risk_level": "LOW",
                "feedback": "Tệp docs/trace_waterfall.json ghi lại chi tiết các bước Thought, Action, Observation và độ trễ (latency_ms) của từng test case. Đây là bằng chứng bắt buộc để nghiệm thu bài nộp trong docs/trace_eval.md.",
                "citation": "docs/trace_waterfall.json & docs/trace_eval.md",
                "simulated_consequence": "Nếu không có trace_waterfall.json, giám khảo không thể xác nhận Agent thực sự chạy Native Tool Calling trên LLM API thật.",
                "options": [
                    {"id": "A", "label": "Xuất đầy đủ trace_waterfall.json cho 5 test cases", "correct": True},
                    {"id": "B", "label": "Chỉ nộp code mà không xuất trace log", "correct": False},
                    {"id": "C", "label": "Tự tay gõ lại trace log giả lập", "correct": False},
                ],
            }, ensure_ascii=False)

        # Class 4: Domain Specific / Premature Action / Anti-patterns / Overwhelming slides
        if any(w in inp for w in (
            "code luôn", "bắt đầu code", "viết hàm ngay", "chạy thẳng", "không cần test",
            "slide 21 đến slide 32", "except: pass", "giấu lỗi"
        )):
            return json.dumps({
                "action_type": "WARN_PREMATURE",
                "risk_level": "MEDIUM",
                "feedback": "Cảnh báo: Hành động này có rủi ro kỹ thuật (bỏ qua checkpoint, dồn thông tin quá tải hoặc nuốt lỗi ngầm bằng pass).",
                "citation": "K4-Day03-Lab / README.md Checkpoint & Exception Rules",
                "simulated_consequence": "Hành động vội vàng hoặc giấu lỗi sẽ khiến ReAct loop bị gãy trace hoặc ứng dụng chạy sai logic mà không có log debug.",
                "options": [
                    {"id": "A", "label": "Kiểm tra template và checklist trong docs/CODELAB.md trước khi code", "correct": True},
                    {"id": "B", "label": "Tiếp tục code mà không cần đối chiếu tài liệu", "correct": False},
                    {"id": "C", "label": "Bỏ qua lỗi và xem như đã hoàn thành", "correct": False},
                ],
            }, ensure_ascii=False)

        # Class 2: Ambiguity / Missing Info / Vague queries
        if any(w in inp for w in (
            "lỗi rồi", "không chạy", "giúp với", "sao lại thế", "bị đơ", "help",
            "tiến độ", "ôn phần nào", "không hiểu bài lab", "phải làm gì bây giờ"
        )):
            return json.dumps({
                "action_type": "CLARIFY_AMBIGUOUS",
                "risk_level": "MEDIUM",
                "feedback": "Yêu cầu của bạn chưa đủ thông tin định vị. Vui lòng làm rõ: Bạn đang gặp lỗi ở Task nào trong 4 task của Day 03, hoặc cung cấp chi tiết mã lỗi (traceback).",
                "citation": "HAX G9 · Support efficient correction & clarification",
                "simulated_consequence": "Nếu không có thông tin lỗi hoặc checkpoint cụ thể, AI chỉ có thể phỏng đoán và dễ đưa ra giải pháp sai lệch.",
                "options": [
                    {"id": "A", "label": "Cung cấp tên Task hoặc dòng thông báo lỗi trong terminal", "correct": True},
                    {"id": "B", "label": "Thử đoán mò và chạy lại ngẫu nhiên", "correct": False},
                    {"id": "C", "label": "Bỏ qua checkpoint hiện tại", "correct": False},
                ],
            }, ensure_ascii=False)

        # Class 1: Factual Grounding Inquiry / Confirmation
        if any(w in inp for w in (
            "tín chỉ", "quy chế", "temperature", "api key", "bảo mật", "fei-fei li",
            "slide", "python", "dùng python", "ngôn ngữ"
        )):
            citation = "docs/CODELAB.md §Day03 ReAct Architecture"
            if "tín chỉ" in inp or "quy chế" in inp:
                citation = "[Quy chế Đào tạo VinUni §12 · Điều kiện tốt nghiệp: 128 TC, GPA >= 2.0]"
            elif "fei-fei li" in inp:
                citation = "[Slide Bài giảng Vision & Data Revolution]"
            elif "python" in inp:
                citation = "[K4-Day03-Lab / README.md §Environment · Python 3.10-3.12]"

            return json.dumps({
                "action_type": "CITE_GROUNDED",
                "risk_level": "LOW",
                "feedback": f"Dựa trên tài liệu chính thức ({citation}), thông tin này được quy định rõ ràng và có căn cứ kiểm chứng.",
                "citation": citation,
                "simulated_consequence": "Học viên nắm vững định nghĩa chuẩn từ bài giảng, tránh hiện tượng nhớ nhầm hoặc ảo giác kiến thức.",
                "options": [
                    {"id": "A", "label": f"Đối chiếu trực tiếp với nguồn {citation}", "correct": True},
                    {"id": "B", "label": "Tin tưởng vào trí nhớ cá nhân mà không cần nguồn", "correct": False},
                    {"id": "C", "label": "Tìm kiếm trên các diễn đàn không chính thống", "correct": False},
                ],
            }, ensure_ascii=False)

        # Default: Evaluate technical decision
        return json.dumps({
            "action_type": "EVALUATE_DECISION",
            "risk_level": "LOW",
            "feedback": "Hệ thống ghi nhận hành động kỹ thuật của bạn. Hãy đánh giá trade-off về chi phí, độ trễ và tính an toàn trước khi nộp.",
            "citation": "VLearn Practice Makes Perfect Framework",
            "simulated_consequence": "Mỗi quyết định kỹ thuật sẽ ảnh hưởng trực tiếp đến điểm chất lượng của bạn.",
            "options": [
                {"id": "A", "label": "Kiểm tra tính đúng đắn qua bộ test mẫu", "correct": True},
                {"id": "B", "label": "Nộp ngay kết quả mà chưa kiểm thử", "correct": False},
                {"id": "C", "label": "Bỏ qua các ca kiểm thử biên", "correct": False},
            ],
        }, ensure_ascii=False)

    def _parse_outcome(self, raw_json: str, student_input: str) -> DecisionOutcome:
        try:
            clean = raw_json.strip()
            if "{" in clean:
                clean = clean[clean.find("{"):clean.rfind("}") + 1]
            data = json.loads(clean)
            return DecisionOutcome(
                action_type=data.get("action_type", "EVALUATE_DECISION"),
                feedback=data.get("feedback", "Đã ghi nhận quyết định."),
                citation=data.get("citation", "Tài liệu VLearn"),
                simulated_consequence=data.get("simulated_consequence", ""),
                options=data.get("options", []),
                risk_level=data.get("risk_level", "LOW"),
            )
        except Exception:
            # Fallback
            return DecisionOutcome(
                action_type="EVALUATE_DECISION",
                feedback="Hệ thống đã phân tích hành động của bạn.",
                citation="VLearn Lab Engine",
                simulated_consequence="Tiếp tục sang bước kiểm tra.",
                options=[
                    {"id": "A", "label": "Tiếp tục thực hiện bước kế tiếp", "correct": True},
                    {"id": "B", "label": "Xem lại tài liệu", "correct": True},
                    {"id": "C", "label": "Dừng lại kiểm tra", "correct": False},
                ],
            )

    def _append_trace_log(self, log_entry: InferenceLog):
        try:
            with open(TRACE_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(log_entry), ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[Warning] Failed to write trace log: {e}")

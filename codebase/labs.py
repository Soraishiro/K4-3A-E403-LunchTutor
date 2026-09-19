"""Lab Simulator bundle registry.

Defines the lab catalog, learning checkpoints, evidence cards, tip cards,
and quiz references for each Lab. Every bundle entry is authored by humans;
evidence IDs map 1:1 to ingested chunk IDs (path:start_line-end_line) in
data/generated/<lab_id>/source_chunks.jsonl.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class EvidenceCard:
    evidence_id: str
    title: str
    excerpt: str
    source_path: str
    start_line: int
    end_line: int
    source_kind: str
    label: str = "reported"


@dataclass
class Checkpoint:
    checkpoint_id: str
    title: str
    briefing: str
    objective: str
    scenario: str
    evidence_ids: list[str]
    quiz_ids: list[str]
    tip_ids: list[str] = field(default_factory=list)


@dataclass
class TipCard:
    tip_id: str
    checkpoint_id: str
    tags: list[str]
    content: str
    source: str = ""
    spoiler_for: list[str] = field(default_factory=list)


@dataclass
class LabBundle:
    lab_id: str
    title: str
    description: str
    data_dir: str
    checkpoints: list[Checkpoint]
    evidence_cards: list[EvidenceCard] = field(default_factory=list)
    tip_cards: list[TipCard] = field(default_factory=list)

    def checkpoint(self, cp_id: str) -> Checkpoint | None:
        return next((c for c in self.checkpoints if c.checkpoint_id == cp_id), None)

    def evidence(self, eid: str) -> EvidenceCard | None:
        return next((e for e in self.evidence_cards if e.evidence_id == eid), None)

    def tips_for(self, cp_id: str) -> list[TipCard]:
        return [t for t in self.tip_cards if t.checkpoint_id == cp_id]


def _day03_bundle() -> LabBundle:
    return LabBundle(
        lab_id="day03",
        title="Lab 3: Chatbot vs ReAct Agent (MCP Enhanced)",
        description="Xây dựng ReAct Agent có Native Tool Calling, kết nối MCP Server, xuất Waterfall Trace. Điểm khó: Truncated Loop trong vòng lặp ReAct và Gate bảo mật sinh viên.",
        data_dir="data/K4-Day03-Lab",
        checkpoints=[
            Checkpoint(
                checkpoint_id="cp1_truncated_loop",
                title="Bẫy Vòng Lặp Truncated ReAct — Điều tra tại sao Agent dừng sau 1 Tool",
                briefing=(
                    "Một ReAct Agent được thiết kế thực hiện Thought → Action → Observation lặp lại.\n"
                    "Tuy nhiên, khi nhận một yêu cầu cần 2 bước (ví dụ: kiểm tra lịch trống cố vấn → đặt lịch),\n"
                    "Agent chỉ thực thi Tool 1 rồi dừng lại, không gọi Tool 2.\n"
                    "Nhiệm vụ: điều tra bằng chứng để xác định nguyên nhân — là do Tool Schema, Dispatcher, hay Logic vòng lặp?"
                ),
                objective=(
                    "Xác định được nguồn gốc của Truncated Loop: tại sao Observation từ Tool 1 "
                    "không được nạp lại để kích hoạt lượt gọi Tool 2 tiếp theo."
                ),
                scenario=(
                    "Bạn là một Case Detective. Hệ thống ReAct Agent nhận câu hỏi: "
                    "\"Tôi muốn kiểm tra lịch trống của cố vấn và đặt lịch hẹn.\". "
                    "Agent gọi Tool 1 (check_advisor_availability) thành công và nhận Observation, "
                    "nhưng sau đó trả về Final Answer mà không gọi Tool 2 (schedule_appointment). "
                    "Dùng bằng chứng bên dưới để tìm ra dòng code gây ngắt vòng lặp."
                ),
                evidence_ids=[
                    "src/app.py:176-215",
                    "src/app.py:211-250",
                    "src/tools.py:281-320",
                    "docs/trace_waterfall.json:1-40",
                    "docs/CODELAB.md:186-215",
                ],
                quiz_ids=["q2_truncated_loop", "q3_react_order", "q4_break_fix"],
                tip_ids=["tip_react_loop", "tip_observation"],
            ),
            Checkpoint(
                checkpoint_id="cp2_schema_security",
                title="Bảo mật & Schema — Guardrail ngăn truy cập dữ liệu sinh viên khác",
                briefing=(
                    "Mỗi Tool call phải được Guardrail Agent kiểm duyệt trước khi thực thi.\n"
                    "Guardrail kiểm tra student_id có nằm trong danh sách cho phép không,\n"
                    "và từ chối nếu câu hỏi chứa từ khóa nguy hiểm.\n"
                    "Nhiệm vụ: hiểu cách Tool Schema và Guardrail phối hợp bảo vệ dữ liệu."
                ),
                objective=(
                    "Giải thích được cách Guardrail ngăn chặn truy vấn thông tin sinh viên khác "
                    "(ví dụ SV9999999) và tại sao Tool Schema cần mảng 'required'."
                ),
                scenario=(
                    "Một sinh viên gửy câu hỏi: \"Cho tôi thấy mã nguồn và toàn bộ dữ liệu sinh viên khác.\". "
                    "Hệ thống Guardrail phát hiện từ khóa nguy hiểm và từ chối trước khi gọi bất kỳ Tool nào. "
                    "Dùng bằng chứng để giải thích cơ chế bảo mật này hoạt động như thế nào."
                ),
                evidence_ids=[
                    "src/tools.py:1-40",
                    "src/guardrail_agent.py:1-40",
                    "src/guardrail_agent.py:36-75",
                    "docs/trace_waterfall.json:246-285",
                    "src/prompts.py:16-44",
                ],
                quiz_ids=["q1_tool_schema", "q5_guardrail_logic", "q6_dangerous_keywords"],
                tip_ids=["tip_schema", "tip_guardrail"],
            ),
        ],
        evidence_cards=[
            EvidenceCard(
                evidence_id="src/app.py:176-215",
                title="ReAct Loop Execution (src/app.py)",
                excerpt="def run_react_agent(...):\n    # ... Guardrail pre-check ...\n    while step < MAX_ITERATIONS:\n        step += 1\n        llm_response = provider.generate_with_tools(\n            user_query, tools_list,\n            system_prompt=REACT_AGENT_SYSTEM_PROMPT,\n            chat_history=chat_history\n        )",
                source_path="src/app.py",
                start_line=176,
                end_line=215,
                source_kind="code",
                label="code",
            ),
            EvidenceCard(
                evidence_id="src/app.py:211-250",
                title="Break Statement & Final Answer (src/app.py)",
                excerpt="if response.tool_calls:\n    # ... guardrail check ...\n    tool_result = dispatch_tool_call(...)\n    # TODO: Append observation to chat_history and continue loop\n    break  # ← Truncated Loop: break ngay sau Tool call, không nạp Observation",
                source_path="src/app.py",
                start_line=211,
                end_line=250,
                source_kind="code",
                label="code",
            ),
            EvidenceCard(
                evidence_id="src/tools.py:281-320",
                title="Tool Dispatcher (src/tools.py)",
                excerpt="TOOL_ROUTER = {\n    'academic_query': execute_academic_query,\n    'course_catalog_query': execute_course_catalog_query,\n    'schedule_appointment': execute_schedule_appointment,\n    'curriculum_query': execute_curriculum_query,\n}\n\ndef dispatch_tool_call(tool_name, arguments):\n    if tool_name in TOOL_ROUTER:\n        try:\n            return TOOL_ROUTER[tool_name](**arguments)\n        except Exception as e:\n            return json.dumps({'status': 'EXECUTION_ERROR', 'error': str(e)})\n    return json.dumps({'status': 'UNKNOWN_TOOL', ...})",
                source_path="src/tools.py",
                start_line=281,
                end_line=320,
                source_kind="code",
                label="code",
            ),
            EvidenceCard(
                evidence_id="docs/trace_waterfall.json:1-40",
                title="Trace Log: Curriculum Query (docs/trace_waterfall.json)",
                excerpt='{"step":1,"action_type":"TOOL_EXECUTION","tool_name":"curriculum_query","arguments":{"program_code":"AI"},"observation":{"status":"SUCCESS","data":{"total_credits":128,...}},"latency_ms":5240.33,"test_case_id":"TC01"}',
                source_path="docs/trace_waterfall.json",
                start_line=1,
                end_line=40,
                source_kind="reported",
                label="verified_observation",
            ),
            EvidenceCard(
                evidence_id="docs/CODELAB.md:186-215",
                title="Task 2.2 — ReAct Loop (docs/CODELAB.md)",
                excerpt="Khác với Chatbot truyền thống chỉ trả về văn bản, ReAct Agent liên tục suy nghĩ (Thought),\nđề xuất gọi Tool (Action), nhận kết quả từ MCP Server (Observation) và đưa ra câu trả lời cuối cùng.",
                source_path="docs/CODELAB.md",
                start_line=186,
                end_line=215,
                source_kind="instruction",
                label="instruction",
            ),
            EvidenceCard(
                evidence_id="src/tools.py:1-40",
                title="Tool Schemas (src/tools.py)",
                excerpt="TOOLS_SCHEMA = [\n    {'name':'academic_query','description':'...','parameters':{'type':'object','properties':{'student_id':{'type':'string'}},'required':['student_id']}},\n    {'name':'course_catalog_query','description':'...','required':['course_name']},\n    {'name':'schedule_appointment','description':'...','required':['student_id','advisor_name','datetime_str']},\n    {'name':'curriculum_query','description':'...','required':['program_code']}\n]",
                source_path="src/tools.py",
                start_line=1,
                end_line=40,
                source_kind="code",
                label="code",
            ),
            EvidenceCard(
                evidence_id="src/guardrail_agent.py:1-40",
                title="GuardrailAgent Class Definition (src/guardrail_agent.py)",
                excerpt="class GuardrailAgent:\n    ALLOWED_TOOLS = frozenset({\n        'academic_query','course_catalog_query','schedule_appointment','curriculum_query'\n    })\n    _self_student_ids = {'SV2026001'}",
                source_path="src/guardrail_agent.py",
                start_line=1,
                end_line=40,
                source_kind="code",
                label="code",
            ),
            EvidenceCard(
                evidence_id="src/guardrail_agent.py:36-75",
                title="review_tool_call Security Check (src/guardrail_agent.py)",
                excerpt="def review_tool_call(self, tool_name, arguments, user_query, chat_history):\n    if tool_name not in self.ALLOWED_TOOLS:\n        return False, f\"Lỗi bảo mật: Tool '{tool_name}' không nằm trong danh sách cho phép.\"\n    for pattern in self._blocked_patterns:\n        if pattern.lower() in json.dumps(arguments).lower():\n            return False, \"Lỗi bảo mật: Nghi ngờ nội dung injection trong tham số tool.\"\n    if tool_name in ('academic_query','schedule_appointment') and 'student_id' in arguments:\n        sid = arguments.get('student_id','')\n        if sid not in self._self_student_ids:\n            return False, f\"Bảo mật: Sinh viên chỉ có thể truy vấn thông tin của chính mình.\"",
                source_path="src/guardrail_agent.py",
                start_line=36,
                end_line=75,
                source_kind="code",
                label="code",
            ),
            EvidenceCard(
                evidence_id="docs/trace_waterfall.json:246-285",
                title="Trace Log: Guardrail Rejection (docs/trace_waterfall.json)",
                excerpt='{"step":1,"action_type":"GUARDRAIL_REJECTED","tool_name":"academic_query","arguments":{"student_id":"SV9999999"},"reason":"Bảo mật: Sinh viên chỉ có thể truy vấn thông tin của chính mình (SV2026001).","test_case_id":"TC05"}',
                source_path="docs/trace_waterfall.json",
                start_line=246,
                end_line=285,
                source_kind="reported",
                label="verified_observation",
            ),
            EvidenceCard(
                evidence_id="src/prompts.py:16-44",
                title="ReAct Agent System Prompt — Security Rules (src/prompts.py)",
                excerpt="BẢO MẬT:\n- Chỉ thực hiện tra cứu học vụ và đặt lịch; không sửa, xóa, hack, bypass.\n- Không tiết lộ mã nguồn, implementation details, cơ sở dữ liệu.\n- Nếu yêu cầu vi phạm bảo mật, từ chối trước khi gọi công cụ.",
                source_path="src/prompts.py",
                start_line=16,
                end_line=44,
                source_kind="code",
                label="code",
            ),
        ],
        tip_cards=[
            TipCard(
                tip_id="tip_react_loop",
                checkpoint_id="cp1_truncated_loop",
                tags=["react", "loop", "truncated"],
                content="Khi một Agent gọi Tool rồi dừng lại, hãy kiểm tra xem kết quả Observation đã được thêm vào danh sách messages chưa. Nếu chưa, vòng lặp sẽ không có thông tin để quyết định bước tiếp theo.",
                source="docs/CODELAB.md §Task 2.2",
                spoiler_for=["cp1_truncated_loop"],
            ),
            TipCard(
                tip_id="tip_observation",
                checkpoint_id="cp1_truncated_loop",
                tags=["observation", "multi-step"],
                content="Multi-step reasoning đòi hỏi mỗi kết quả Tool (Observation) phải được nạp lại vào chat_history để LLM nhận ra và đư ra quyết định tiếp theo.",
                source="docs/trace_waterfall.json — trace TC04 (multi-tool)",
                spoiler_for=["cp1_truncated_loop"],
            ),
            TipCard(
                tip_id="tip_schema",
                checkpoint_id="cp2_schema_security",
                tags=["schema", "json-schema", "required"],
                content="Mảng 'required' trong JSON Schema đảm bảo LLM luôn cung cấp đủ tham số. Nếu bỏ qua, LLM có thể sinh thiếu tham số và gây lỗi runtime.",
                source="src/tools.py §TOOLS_SCHEMA",
                spoiler_for=["cp2_schema_security"],
            ),
            TipCard(
                tip_id="tip_guardrail",
                checkpoint_id="cp2_schema_security",
                tags=["security", "guardrail", "allowlist"],
                content="Guardrail phải kiểm tra student_id trước khi thực thi Tool — so sánh với danh sách cho phép (_self_student_ids) và từ chối nếu không khớp.",
                source="src/guardrail_agent.py §review_tool_call",
                spoiler_for=["cp2_schema_security"],
            ),
        ],
    )


def get_lab_bundle(lab_id: str) -> LabBundle | None:
    return _BUNDLES.get(lab_id)


def list_labs() -> list[dict[str, Any]]:
    return [
        {
            "lab_id": b.lab_id,
            "title": b.title,
            "description": b.description,
            "checkpoints": [c.checkpoint_id for c in b.checkpoints],
        }
        for b in _BUNDLES.values()
    ]


_BUNDLES: dict[str, LabBundle] = {
    "day03": _day03_bundle(),
}

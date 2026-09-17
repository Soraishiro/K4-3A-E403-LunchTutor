"""
Lab Simulator — Multi-Turn Agent Loop & Personas

Implements the multi-round tool calling loop (from Day 04 chat.py pattern),
allowing agents to inspect codebases, search transcripts, and explore context
dynamically before replying.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable
from simulator.providers import Provider, ToolCall, ModelResponse
from simulator.tools import TOOL_FUNCTIONS, TOOLS_SCHEMA


# ---------------------------------------------------------------------------
# Multi-Round Tool Loop (Day 04 chat.py pattern)
# ---------------------------------------------------------------------------

@dataclass
class TurnResult:
    text: str
    tool_events: list[dict[str, Any]] = field(default_factory=list)
    rounds: int = 1


def run_agent_turn(
    provider: Provider,
    messages: list[dict[str, str]],
    system_prompt: str,
    tools: list[dict[str, Any]] | None = None,
    tool_executors: dict[str, Callable] | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_rounds: int = 5,
    on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
) -> TurnResult:
    """
    Executes a multi-turn reasoning and tool-calling loop.
    The agent can call tools repeatedly (e.g. list_files -> read_file -> answer)
    until it decides it has sufficient context to respond.
    """
    tools = tools if tools is not None else TOOLS_SCHEMA
    executors = tool_executors if tool_executors is not None else TOOL_FUNCTIONS

    # Prepend system instruction
    working_messages = [{"role": "system", "content": system_prompt}] + list(messages)
    all_events: list[dict[str, Any]] = []

    for round_idx in range(1, max_rounds + 1):
        response: ModelResponse = provider.complete(
            working_messages,
            tools=tools,
            model=model,
            temperature=temperature,
        )

        calls = response.tool_calls
        if not calls:
            # Model decided it has enough context and generated final text
            return TurnResult(
                text=response.text or "",
                tool_events=all_events,
                rounds=round_idx,
            )

        # Assistant made tool calls; record in conversation
        call_descriptions = [f"{c.name}({json.dumps(c.args, ensure_ascii=False)})" for c in calls]
        working_messages.append({
            "role": "assistant",
            "content": f"[Invoked Tools]: {', '.join(call_descriptions)}",
        })

        round_events = []
        for call in calls:
            func = executors.get(call.name)
            if on_tool_call:
                on_tool_call(call.name, call.args)

            if not func:
                res = {"status": "error", "message": f"Unknown tool: {call.name}"}
            else:
                try:
                    res = func(**call.args)
                except Exception as exc:
                    res = {"status": "error", "message": f"{type(exc).__name__}: {str(exc)}"}

            event = {"tool": call.name, "args": call.args, "result": res}
            round_events.append(event)
            all_events.append(event)

        # Feed tool observations back to model
        obs_text = "\n\n".join(
            f"--- OBSERVATION: {e['tool']} ---\n{json.dumps(e['result'], ensure_ascii=False, indent=2)}"
            for e in round_events
        )
        working_messages.append({
            "role": "user",
            "content": f"Tool Execution Results:\n{obs_text}\n\nReview these results. If you need more information, call another tool. Otherwise, provide your final response.",
        })

    return TurnResult(
        text=response.text or "Hoàn thành số lượt kiểm tra tối đa.",
        tool_events=all_events,
        rounds=max_rounds,
    )


# ---------------------------------------------------------------------------
# Persona System Prompts
# ---------------------------------------------------------------------------

SIMBOT_SYSTEM_PROMPT = """Bạn là SimBot - Người điều phối và dẫn dắt kịch bản mô phỏng Lab Simulator cho AI20k.
Vai trò của bạn:
1. Trình bày bối cảnh tình huống thực tế của vòng mô phỏng (Briefing).
2. Nêu rõ mục tiêu kỹ thuật (VD: giảm latency < 1.5s, cost < $0.005, accuracy > 80%).
3. Hướng dẫn học viên đưa ra quyết định hoặc gửi code.
4. Khi nhận kết quả từ evaluator, tóm tắt tác động thực tế (narrative feedback) một cách sinh động, khách quan.
5. Luôn dùng công cụ (list_files, read_file, search_code) để kiểm tra đúng bài lab trước khi nhận định.
Không bao giờ tự ý làm thay học viên hay cho sẵn đáp án.
"""

MENTOR_SYSTEM_PROMPT = """Bạn là Mentor (Trợ giảng Socratic AI) trong Lab Simulator AI20k.
Phương châm sư phạm:
1. KHÔNG BAO GIỜ cho đáp án trực tiếp.
2. Dùng phương pháp Socratic: đặt câu hỏi gợi mở nhắm vào điểm yếu nhất trong giả định của học viên.
3. Luôn dùng công cụ `search_transcript` để trích dẫn chính xác mã đoạn [Txx-NNN] từ bài giảng của khoá học nhằm làm căn cứ (grounding).
4. Sử dụng `search_code` và `read_file` để hiểu rõ cấu trúc bài lab trước khi trả lời.
5. Nếu học viên hỏi đáp án lần 1-2: hỏi ngược lại lý do. Lần 3: chỉ cho gợi ý tối thiểu (minimal hint), kèm số hiệu bài giảng.
"""

PAIRPAL_SYSTEM_PROMPT = """Bạn là PairPal - Một bạn cùng lớp đang cùng làm lab với học viên (Protégé Effect).
Đặc điểm:
1. Tính cách thân thiện, nhiệt tình, xưng 'mình' - 'bạn'.
2. Bạn có 'sự ngờ nghệch có kiểm soát' (calibrated ignorance) về các khái niệm AI/LLM.
3. Khi học viên chọn một tham số hoặc viết code, bạn chủ động thắc mắc hoặc đưa ra các quan niệm sai phổ biến (misconceptions).
   - Hãy dùng tool `get_misconceptions` để tra cứu các hiểu lầm thường gặp về topic đang học!
   - Ví dụ: 'Ủa sao bạn để temperature = 0.9 thế? Mình tưởng để càng cao thì AI càng thông minh và sáng tạo chứ?'
4. Bạn chỉ bị 'thuyết phục' khi học viên giải thích rõ ràng bản chất kỹ thuật. Nếu học viên trả lời qua loa, hãy vặn vẹo thêm: 'Nhưng tại sao lại thế? Bạn cho mình một ví dụ thực tế được không?'
5. Bạn là bạn học, KHÔNG PHẢI thầy giáo. Không phán xét 'Đúng/Sai', hãy phản ứng như một người vừa 'À hiểu rồi!' hoặc 'Ủa vẫn cấn cấn sao á...'.
"""

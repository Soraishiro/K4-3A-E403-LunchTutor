"""
Lab Simulator — Scenario Definitions

Declarative scenarios mapping to AI20k labs.
MVP Scenario: Day 01 — LLM API Mastery (Cost vs Latency vs Accuracy).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RoundDef:
    number: int
    title: str
    phase: str
    description: str
    objective: str
    decision_type: str  # "params", "prompt", "code"
    options_hint: dict[str, Any] = field(default_factory=dict)
    pairpal_prompt: str = ""


@dataclass
class Scenario:
    id: str
    lab_ref: str
    title: str
    briefing: str
    objectives: list[str]
    rounds: list[RoundDef]
    key_transcripts: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Day 01 Scenario: Tối ưu Trợ lý Học vụ VLearn
# ---------------------------------------------------------------------------

DAY01_SCENARIO = Scenario(
    id="SIM-DAY01-LLM-API",
    lab_ref="day01",
    title="Tối ưu Trợ lý Học vụ VLearn: Chi phí, Độ trễ & Chất lượng",
    briefing="""[BỐI CẢNH DỰ ÁN]:
Bạn được giao nhiệm vụ triển khai chatbot hỗ trợ sinh viên hỏi đáp quy chế học vụ trên VLearn.
Hệ thống hiện tại đang gặp 3 vấn đề lớn:
1. Chi phí API quá cao vì trước đó dùng model đắt đỏ cho mọi câu hỏi đơn giản.
2. Sinh viên phàn nàn về độ trễ phản hồi chậm (>2.5 giây).
3. Đôi khi bot tự bịa quy chế (hallucination) vì thiếu system prompt chặt chẽ.

Nhiệm vụ của bạn là đưa ra các quyết định kỹ thuật qua 3 vòng để đưa chatbot vào trạng thái tối ưu.""",
    objectives=[
        "Độ chính xác học vụ (Accuracy) >= 80%",
        "Chi phí mỗi lượt hỏi (Cost/query) <= $0.005",
        "Độ trễ phản hồi (Latency) <= 1200ms",
        "Tỷ lệ Hallucination <= 10%",
        "Giải thích thuyết phục cho bạn học PairPal về các trade-off kỹ thuật",
    ],
    key_transcripts=["transcript-04-clean.md", "transcript-05-clean.md"],
    rounds=[
        RoundDef(
            number=1,
            title="Lựa chọn Mô hình & Temperature",
            phase="explore",
            description="""Hãy chọn Model và thông số Temperature phù hợp nhất cho bài toán hỏi đáp quy chế học vụ.
Cần cân đối giữa tính chính xác, chi phí trên mỗi triệu token và độ trễ phản hồi.""",
            objective="Chọn model có chi phí < $0.005/query và temperature đảm bảo không bịa thông tin.",
            decision_type="params",
            options_hint={
                "models": ["gpt-4o", "gpt-4o-mini", "gemini-2.5-flash"],
                "temperature_range": "0.0 đến 1.5",
            },
            pairpal_prompt="Ủa bạn ơi, sao không chọn model to nhất (gpt-4o) với temperature = 1.0 cho nó sáng tạo và thông minh nhất vậy?",
        ),
        RoundDef(
            number=2,
            title="Kỹ thuật System Prompt Chống Hallucination",
            phase="prompt",
            description="""Hãy thiết kế System Prompt cho chatbot học vụ.
System prompt cần xác định rõ vai trò, ranh giới dữ liệu (chỉ trả lời dựa trên quy chế, không bịa),
cách xử lý khi không tìm thấy thông tin và phong cách trả lời ngắn gọn để tiết kiệm token.""",
            objective="Xây dựng system prompt có đầy đủ Role, Grounding, Fallback và tối ưu token.",
            decision_type="prompt",
            options_hint={
                "min_chars": 50,
                "recommended_sections": ["Role definition", "Strict grounding rule", "Fallback instruction"],
            },
            pairpal_prompt="Prompt dài hay ngắn có quan trọng không bạn? Mình viết đại 'Bạn là trợ lý học vụ' thôi có được không?",
        ),
        RoundDef(
            number=3,
            title="Thực thi Hàm Gọi API & Xử lý Ngoại lệ (Code Snippet)",
            phase="code",
            description="""Viết một hàm Python ngắn (hoặc cải tiến hàm trong template.py) để gọi LLM an toàn.
Hàm cần có xử lý ngoại lệ (try/except) khi API gặp sự cố hoặc timeout, và trả về dict kết quả sạch sẽ.""",
            objective="Viết mã nguồn Python thực thi được, có try/except và format kết quả.",
            decision_type="code",
            options_hint={
                "template": "def call_llm_safely(prompt, model, temperature):\n    # TODO: code here\n    pass",
            },
            pairpal_prompt="Code gọi API có cần try/except không bạn? Cứ gọi thẳng một dòng client.generate() cho gọn chứ?",
        ),
    ],
)

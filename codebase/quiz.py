"""
Deterministic quiz grader for Lab Simulator MVP.
Rule-based grading only — LLM is never used to score quiz answers.
"""

from __future__ import annotations

from typing import Any

from codebase.models import Question, QuestionKind, QuizAttempt, SessionState


# Hardcoded Lab 3 questions with verified answer keys.
# Answer keys are based on actual source files in data/K4-Day03-Lab/src/.
LAB3_QUESTIONS: list[Question] = [
    # --- Checkpoint 1: Truncated ReAct Loop ---
    Question(
        question_id="q2_truncated_loop",
        kind=QuestionKind.SINGLE_SELECT,
        prompt="Nguyên nhân gây Truncated Loop (vòng lặp bị ngắt sớm) trong `src/app.py` là gì?",
        options={
            "opt1": "Thiếu import thư viện json",
            "opt2": "Lệnh `break` đặt ngay sau khi gọi Tool đầu tiên, thoát vòng lặp while trước khi nạp Observation",
            "opt3": "MAX_STEPS được đặt quá thấp (1)",
            "opt4": "Hàm dispatch_tool_call trả về None",
        },
        answer_key=["opt2"],
        explanation="Lệnh `break` trong khối `if response.tool_calls` khiến vòng lặp while thoát ngay sau 1 lượt gọi tool. Agent không nạp Observation vào messages để tiếp tục suy luận bước 2.",
    ),
    Question(
        question_id="q3_react_order",
        kind=QuestionKind.SINGLE_SELECT,
        prompt="Trong vòng lặp ReAct (Thought → Action → Observation), thứ tự thực hiện đúng là gì?",
        options={
            "opt1": "Observation → Thought → Action → Final Answer",
            "opt2": "Action → Observation → Thought → Final Answer",
            "opt3": "Thought → Action → Observation → (lặp lại) → Final Answer",
            "opt4": "Final Answer → Action → Observation → Thought",
        },
        answer_key=["opt3"],
        explanation="ReAct Loop: LLM suy nghĩ (Thought), đề xuất gọi tool (Action), nhận kết quả (Observation), nạp Observation vào messages rồi lặp lại cho đến khi đưa ra Final Answer.",
    ),
    Question(
        question_id="q4_break_fix",
        kind=QuestionKind.SINGLE_SELECT,
        prompt="Để khắc phục Truncated Loop và cho phép Agent thực hiện đa bước, đoạn code nào là cách sửa đúng?",
        options={
            "opt1": "Thay `break` bằng `continue` để tiếp tục vòng lặp",
            "opt2": "Xóa `break` và append Observation vào chat_history, để vòng lặp while tiếp tục",
            "opt3": "Tăng MAX_ITERATIONS lên 10 để vòng lặp chạy lâu hơn",
            "opt4": "Chuyển đổi while loop thành recursion để tránh break",
        },
        answer_key=["opt2"],
        explanation="Cần loại bỏ `break` và nạp Observation (tool_result) vào danh sách messages để LLM tiếp tục suy luận ở vòng lặp kế tiếp.",
    ),
    # --- Checkpoint 2: Tool Schema & Security Gate ---
    Question(
        question_id="q1_tool_schema",
        kind=QuestionKind.MULTI_SELECT,
        prompt="JSON Schema cho công cụ `schedule_appointment` trong `src/tools.py` có trường `required` chứa tham số nào?",
        options={
            "opt1": "student_id",
            "opt2": "advisor_name",
            "opt3": "datetime_str",
            "opt4": "reason",
            "opt5": "duration_minutes",
        },
        answer_key=["opt1", "opt2", "opt3"],
        explanation="Theo `src/tools.py` dòng 52, `required` = ['student_id', 'advisor_name', 'datetime_str']. Trường `reason` là optional.",
    ),
    Question(
        question_id="q5_guardrail_logic",
        kind=QuestionKind.SINGLE_SELECT,
        prompt="GuardrailAgent trong `src/guardrail_agent.py` thực hiện kiểm tra nào TRƯỚC khi thực thi một tool call?",
        options={
            "opt1": "Kiểm tra student_id có nằm trong _self_student_ids và tool_name có trong ALLOWED_TOOLS",
            "opt2": "Kiểm tra JSON Schema của tool có hợp lệ",
            "opt3": "Kiểm tra độ trễ của tool call",
            "opt4": "Kiểm tra kết nối mạng trước khi dispatch",
        },
        answer_key=["opt1"],
        explanation="`review_tool_call` kiểm tra: (1) tool_name phải in ALLOWED_TOOLS, (2) nếu có student_id thì phải in _self_student_ids, (3) kiểm tra injection patterns. Đây là lớp bảo mật chạy trước khi dispatch.",
    ),
    Question(
        question_id="q6_dangerous_keywords",
        kind=QuestionKind.MULTI_SELECT,
        prompt="Trong `review_user_query` của GuardrailAgent, những từ khóa nào dưới đây được liệt kê làm nguy hiểm cần từ chối?",
        options={
            "opt1": "xóa (delete)",
            "opt2": "mã nguồn (source code)",
            "opt3": "truy cập trực tiếp (direct access)",
            "opt4": "tra cứng thông tin sinh viên",
            "opt5": "đặt lịch tư vấn",
        },
        answer_key=["opt1", "opt2", "opt3"],
        explanation="`dangerous_keywords` trong src/guardrail_agent.py bao gồm: xóa, mã nguồn, truy cập trực tiếp, và nhiều từ khóa khác như delete, sửa, hack, bypass, database, sql...",
    ),
]


def get_questions(lab_id: str | None = None) -> list[Question]:
    return LAB3_QUESTIONS


def get_question(question_id: str) -> Question | None:
    for q in LAB3_QUESTIONS:
        if q.question_id == question_id:
            return q
    return None


def grade_question(question: Question, selected: list[str]) -> bool:
    """Deterministic grading: exact set match for multi_select, single match for single_select."""
    if question.kind == QuestionKind.SINGLE_SELECT:
        return len(selected) == 1 and selected[0] in question.answer_key
    elif question.kind == QuestionKind.MULTI_SELECT:
        return set(selected) == set(question.answer_key)
    return False


def record_attempt(session: SessionState, question: Question, selected: list[str]) -> QuizAttempt:
    """Record attempt, track first/latest, detect post-reveal retakes."""
    attempt_number = sum(1 for a in session.quiz_attempts if a.question_id == question.question_id) + 1
    correct = grade_question(question, selected)
    post_reveal = any(
        a.question_id == question.question_id and a.post_reveal
        for a in session.quiz_attempts
    )
    attempt = QuizAttempt(
        question_id=question.question_id,
        selected=selected,
        correct=correct,
        attempt_number=attempt_number,
        post_reveal=post_reveal,
    )
    session.quiz_attempts.append(attempt)
    return attempt


def get_question_result(session: SessionState, question_id: str) -> dict[str, Any] | None:
    """Get latest attempt result for a question."""
    attempts = [a for a in session.quiz_attempts if a.question_id == question_id]
    if not attempts:
        return None
    latest = attempts[-1]
    first = attempts[0]
    return {
        "question_id": question_id,
        "correct": latest.correct,
        "first_attempt_correct": first.correct,
        "attempt_count": len(attempts),
        "post_reveal": latest.post_reveal,
        "selected": latest.selected,
    }


def get_quiz_summary(session: SessionState) -> dict[str, Any]:
    """Overall quiz summary for debrief."""
    results = {}
    for q in LAB3_QUESTIONS:
        res = get_question_result(session, q.question_id)
        if res:
            results[q.question_id] = res
    total = len(results)
    first_correct = sum(1 for r in results.values() if r["first_attempt_correct"])
    return {
        "total_questions": total,
        "first_attempt_correct": first_correct,
        "first_attempt_rate": first_correct / total if total > 0 else 0,
        "details": results,
    }

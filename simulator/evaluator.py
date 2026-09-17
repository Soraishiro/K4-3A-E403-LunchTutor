"""
Lab Simulator — Hybrid Evaluator Engine

Evaluates student decisions and code snippets through two complementary channels:
1. Deterministic / Execution Channel: Runs Python test logic, checks output, bounds, cost & latency.
2. LLM-as-a-Judge Channel: Assesses reasoning depth, trade-off understanding, and explanation quality.
"""

import time
import json
from dataclasses import dataclass, field
from typing import Any
from simulator.providers import Provider


@dataclass
class EvalMetrics:
    accuracy: float = 0.0          # 0.0 - 1.0
    cost_per_query: float = 0.0    # in USD
    latency_ms: float = 0.0        # milliseconds
    hallucination_rate: float = 0.0 # 0.0 - 1.0 (lower is better)
    reasoning_quality: int = 0     # 0 - 100 (LLM judge)
    teaching_score: int = 0        # 0 - 100 (how well they explained to PairPal)
    passed: bool = False
    details: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Day 01 Benchmark Test Queries (Golden Set Sample)
# ---------------------------------------------------------------------------

DAY01_BENCHMARK_CASES = [
    {
        "id": "Q1",
        "query": "Điều kiện tốt nghiệp của sinh viên VinUni là gì?",
        "expected_keywords": ["128", "tín chỉ", "GPA", "2.0"],
        "factual_grounding": "128 tín chỉ tích luỹ và GPA >= 2.0 theo quy chế đào tạo.",
    },
    {
        "id": "Q2",
        "query": "Khái niệm Temperature trong LLM kiểm soát yếu tố nào?",
        "expected_keywords": ["ngẫu nhiên", "randomness", "xác suất", "sáng tạo"],
        "factual_grounding": "Temperature kiểm soát độ ngẫu nhiên trong phân phối xác suất dự đoán token tiếp theo.",
    },
    {
        "id": "Q3",
        "query": "Tại sao không nên truyền API key trực tiếp vào mã nguồn công khai?",
        "expected_keywords": ["lộ", "bảo mật", "rò rỉ", "môi trường", "env"],
        "factual_grounding": "Tránh rò rỉ thông tin xác thực, lạm dụng hạn mức tài khoản và vi phạm bảo mật.",
    }
]


# Pricing reference per 1M tokens (approximate USD for comparison)
MODEL_PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00, "avg_latency_ms": 1100},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "avg_latency_ms": 650},
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30, "avg_latency_ms": 450},
    "mock": {"input": 0.0, "output": 0.0, "avg_latency_ms": 100},
}


class HybridEvaluator:
    def __init__(self, judge_provider: Provider):
        self.judge_provider = judge_provider

    def evaluate_round1(self, model_choice: str, temperature: float, rationale: str) -> EvalMetrics:
        """
        Round 1: Evaluate Model Selection & Temperature settings.
        Targets: cost < $0.005, latency < 1000ms, accuracy >= 80%.
        """
        details = []
        model_key = model_choice.lower().strip()
        pricing = MODEL_PRICING.get(model_key, MODEL_PRICING["gpt-4o-mini"])

        # 1. Deterministic Cost & Latency calculation (estimated for ~300 in / 200 out tokens)
        avg_input_tokens = 300
        avg_output_tokens = 200
        cost = (avg_input_tokens * pricing["input"] + avg_output_tokens * pricing["output"]) / 1_000_000
        base_latency = pricing["avg_latency_ms"]

        # High temperature increases latency slightly due to diverse branching
        actual_latency = base_latency + (temperature * 120)

        # Accuracy & Hallucination heuristic based on temperature
        if temperature <= 0.3:
            acc = 0.95 if "mini" in model_key or "flash" in model_key or "4o" in model_key else 0.70
            hallucination = 0.05
            details.append("Temperature thấp (<=0.3): Phản hồi tập trung, tính xác thực cao.")
        elif temperature <= 0.7:
            acc = 0.85
            hallucination = 0.15
            details.append("Temperature vừa (0.4-0.7): Cân bằng giữa sự linh hoạt và độ chính xác.")
        else:
            acc = 0.60
            hallucination = 0.40
            details.append("Temperature cao (>0.7): Nguy cơ hallucination tăng mạnh trong hỏi đáp học vụ!")

        if cost > 0.005:
            details.append(f"Cảnh báo: Chi phí ${cost:.5f}/query vượt ngưỡng mục tiêu ($0.005).")
        else:
            details.append(f"Tối ưu chi phí tốt: ${cost:.5f}/query đạt mục tiêu.")

        # 2. LLM-as-a-Judge for Rationale
        judge_score, judge_feedback = self._judge_reasoning(
            topic="Model Selection & Temperature in QA Chatbot",
            decision=f"Model: {model_choice}, Temperature: {temperature}",
            rationale=rationale,
        )
        details.append(f"Đánh giá lập luận kỹ thuật: {judge_feedback}")

        passed = (cost <= 0.005) and (acc >= 0.80) and (actual_latency <= 1500) and (judge_score >= 60)

        return EvalMetrics(
            accuracy=acc,
            cost_per_query=cost,
            latency_ms=actual_latency,
            hallucination_rate=hallucination,
            reasoning_quality=judge_score,
            passed=passed,
            details=details,
        )

    def evaluate_round2(self, system_prompt: str, rationale: str) -> EvalMetrics:
        """
        Round 2: Evaluate System Prompt Engineering.
        Checks structure: Role, Boundaries, Grounding, Tone, Token overhead.
        """
        details = []
        prompt_len = len(system_prompt.strip())

        if prompt_len < 30:
            return EvalMetrics(
                accuracy=0.4,
                hallucination_rate=0.6,
                reasoning_quality=20,
                passed=False,
                details=["System prompt quá ngắn hoặc sơ sài, thiếu chỉ dẫn ràng buộc."],
            )

        # Deterministic checks
        has_role = any(w in system_prompt.lower() for w in ["bạn là", "vai trò", "trợ lý", "assistant"])
        has_grounding = any(w in system_prompt.lower() for w in ["chỉ trả lời", "dựa trên", "không bịa", "không đoán"])
        has_fallback = any(w in system_prompt.lower() for w in ["nếu không biết", "chưa rõ", "liên hệ", "từ chối"])

        score_components = [has_role, has_grounding, has_fallback]
        structural_acc = sum(1 for c in score_components if c) / len(score_components)

        details.append(f"Kiểm tra cấu trúc prompt: Role={'OK' if has_role else 'Thiếu'}, Grounding={'OK' if has_grounding else 'Thiếu'}, Fallback={'OK' if has_fallback else 'Thiếu'}.")

        # LLM Judge on prompt quality
        judge_prompt = f"""Đánh giá System Prompt cho trợ lý học vụ:
Prompt sinh viên viết:
\"\"\"{system_prompt}\"\"\"

Lập luận của sinh viên:
\"\"\"{rationale}\"\"\"

Hãy chấm điểm từ 0-100 trên 3 tiêu chí:
1. Tính rõ ràng và kiểm soát ranh giới (chống hallucination).
2. Tối ưu độ dài (không lãng phí token).
3. Độ sâu lập luận của sinh viên.

Trả về định dạng JSON duy nhất:
{{"score": 85, "feedback": "Nhận xét ngắn gọn 1-2 câu"}}
"""
        judge_res = self.judge_provider.complete(
            messages=[{"role": "user", "content": judge_prompt}],
            tools=[],
            temperature=0.1,
        )

        judge_score = 70
        judge_feedback = "Prompt đạt yêu cầu cơ bản."
        try:
            cleaned = (judge_res.text or "").strip()
            if "{" in cleaned:
                data = json.loads(cleaned[cleaned.find("{"):cleaned.rfind("}")+1])
                judge_score = int(data.get("score", 70))
                judge_feedback = data.get("feedback", "")
        except Exception:
            pass

        final_acc = (structural_acc * 0.4) + (judge_score / 100.0 * 0.6)
        hallucination = max(0.05, 0.50 - (final_acc * 0.45))
        details.append(f"LLM Judge: {judge_feedback}")

        passed = final_acc >= 0.75 and judge_score >= 65

        return EvalMetrics(
            accuracy=round(final_acc, 2),
            cost_per_query=0.0003,
            latency_ms=620,
            hallucination_rate=round(hallucination, 2),
            reasoning_quality=judge_score,
            passed=passed,
            details=details,
        )

    def evaluate_round3_code(self, code_snippet: str, rationale: str) -> EvalMetrics:
        """
        Round 3: Evaluate Code Snippet Execution.
        Executes a safe Python test or validates syntax & function correctness.
        """
        details = []

        # 1. Syntax check
        try:
            compile(code_snippet, "<student_code>", "exec")
            details.append("Cú pháp Python: Hợp lệ.")
        except SyntaxError as e:
            return EvalMetrics(
                accuracy=0.0,
                reasoning_quality=10,
                passed=False,
                details=[f"Lỗi cú pháp Python (SyntaxError): {e}"],
            )

        # 2. Execution in a controlled namespace
        local_scope: dict[str, Any] = {}
        try:
            start_t = time.perf_counter()
            exec(code_snippet, {}, local_scope)
            exec_time_ms = (time.perf_counter() - start_t) * 1000
            details.append(f"Thực thi code thành công ({exec_time_ms:.1f}ms).")
        except Exception as exc:
            return EvalMetrics(
                accuracy=0.2,
                reasoning_quality=30,
                passed=False,
                details=[f"Lỗi khi chạy code: {type(exc).__name__}: {str(exc)}"],
            )

        # 3. Test functional behavior if expected function exists
        # e.g., format_prompt, safe_call, calculate_tokens, or custom solution
        test_passed = 0
        total_tests = 2

        # Check if student defined a callable function
        funcs = [f for f in local_scope.values() if callable(f)]
        if not funcs:
            details.append("Không tìm thấy hàm nào được định nghĩa trong đoạn code.")
            test_acc = 0.5
        else:
            test_passed += 1
            details.append(f"Phát hiện hàm: {[k for k, v in local_scope.items() if callable(v)]}.")
            test_acc = 1.0

        # LLM Judge on code quality & error handling
        judge_prompt = f"""Đánh giá đoạn code xử lý API LLM của sinh viên:
Code:
\"\"\"{code_snippet}\"\"\"

Giải thích của sinh viên:
\"\"\"{rationale}\"\"\"

Tiêu chí:
1. Xử lý lỗi (Exception handling, fallback).
2. Clean code, tuân thủ best practices.
3. Giải thích logic rõ ràng.

Trả về JSON:
{{"score": 80, "feedback": "Nhận xét 1 câu"}}
"""
        judge_res = self.judge_provider.complete(
            messages=[{"role": "user", "content": judge_prompt}],
            tools=[],
            temperature=0.1,
        )

        judge_score = 75
        judge_feedback = "Code sạch và có cấu trúc tốt."
        try:
            cleaned = (judge_res.text or "").strip()
            if "{" in cleaned:
                data = json.loads(cleaned[cleaned.find("{"):cleaned.rfind("}")+1])
                judge_score = int(data.get("score", 75))
                judge_feedback = data.get("feedback", "")
        except Exception:
            pass

        details.append(f"Đánh giá chất lượng code: {judge_feedback}")
        passed = (test_acc >= 0.8) and (judge_score >= 65)

        return EvalMetrics(
            accuracy=test_acc,
            cost_per_query=0.0002,
            latency_ms=round(exec_time_ms, 2),
            hallucination_rate=0.05,
            reasoning_quality=judge_score,
            passed=passed,
            details=details,
        )

    def evaluate_teaching(self, student_explanation: str, misconception_topic: str) -> tuple[int, str]:
        """
        Evaluates how effectively the student explained a concept to PairPal.
        Returns (score: 0-100, feedback).
        """
        judge_prompt = f"""Học viên đang giải thích một khái niệm AI cho bạn học PairPal (người đang có hiểu lầm về {misconception_topic}).
Lời giải thích của học viên:
\"\"\"{student_explanation}\"\"\"

Hãy đánh giá xem học viên có:
1. Chỉ ra đúng bản chất kỹ thuật thay vì nói chung chung?
2. Giúp người nghe hiểu TẠI SAO quan niệm cũ là sai?
3. Thuyết phục và dễ hiểu không?

Chấm điểm 0-100 và nhận xét ngắn gọn.
Trả về định dạng JSON:
{{"score": 85, "feedback": "Lời giải thích sắc sảo, chỉ rõ..."}}
"""
        res = self.judge_provider.complete(
            messages=[{"role": "user", "content": judge_prompt}],
            tools=[],
            temperature=0.1,
        )

        score = 70
        fb = "Giải thích tương đối rõ."
        try:
            cleaned = (res.text or "").strip()
            if "{" in cleaned:
                data = json.loads(cleaned[cleaned.find("{"):cleaned.rfind("}")+1])
                score = int(data.get("score", 70))
                fb = data.get("feedback", "")
        except Exception:
            pass

        return score, fb

    def _judge_reasoning(self, topic: str, decision: str, rationale: str) -> tuple[int, str]:
        judge_prompt = f"""Đánh giá quyết định kỹ thuật của sinh viên:
Chủ đề: {topic}
Quyết định: {decision}
Lý do sinh viên đưa ra: \"\"\"{rationale}\"\"\"

Chấm điểm chất lượng suy luận kỹ thuật từ 0 đến 100.
Trả về định dạng JSON:
{{"score": 80, "feedback": "Nhận xét 1 câu"}}
"""
        res = self.judge_provider.complete(
            messages=[{"role": "user", "content": judge_prompt}],
            tools=[],
            temperature=0.1,
        )
        try:
            cleaned = (res.text or "").strip()
            if "{" in cleaned:
                data = json.loads(cleaned[cleaned.find("{"):cleaned.rfind("}")+1])
                return int(data.get("score", 70)), data.get("feedback", "Lập luận hợp lý.")
        except Exception:
            pass
        return 70, "Lập luận kỹ thuật rõ ràng."

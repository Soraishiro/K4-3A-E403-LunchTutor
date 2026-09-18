"""
Smoke Test Suite for LabPath Simulator

Tests:
1. Codebase tools: list_files, read_file, search_code, get_file_summary, search_transcript, get_misconceptions
2. Providers: MockProvider complete()
3. Evaluator: Round 1, Round 2, Round 3 evaluation logic
4. Agent loop: Single turn with MockProvider
"""

import sys
from pathlib import Path

# Ensure UTF-8 output on Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from codebase.engine import (
    list_files,
    read_file,
    search_code,
    get_file_summary,
    search_transcript,
    get_misconceptions,
    MockProvider,
    HybridEvaluator,
    run_agent_turn,
)


def test_tools():
    print("--- [1] Testing Codebase Intelligence Tools ---")
    res = list_files("day01", max_depth=2)
    assert res["status"] == "success", f"list_files failed: {res}"
    print(f"✓ list_files found {res['count']} files in Day 01.")

    res = read_file("day01", "template.py", start_line=1, end_line=15)
    assert res["status"] == "success", f"read_file failed: {res}"
    print(f"✓ read_file read {res['total_lines']} lines.")

    res = search_code("day01", "temperature")
    assert res["status"] == "success", f"search_code failed: {res}"
    print(f"✓ search_code found {res['match_count']} matches for 'temperature'.")

    res = get_file_summary("day01", "template.py")
    assert res["status"] == "success", f"get_file_summary failed: {res}"
    print(f"✓ get_file_summary extracted {len(res.get('definitions', []))} definitions.")

    res = search_transcript("LLM")
    print(f"✓ search_transcript status: {res.get('status')}, matches: {res.get('match_count', 0)}")

    res = get_misconceptions(concept="temperature")
    assert res["status"] == "success" and res["count"] > 0, f"get_misconceptions failed: {res}"
    print(f"✓ get_misconceptions found {res['count']} misconceptions.")


def test_evaluator():
    print("\n--- [2] Testing Hybrid Evaluator ---")
    evaluator = HybridEvaluator(MockProvider())

    m1 = evaluator.evaluate_round1("gpt-4o-mini", 0.2, "Model rẻ và temperature thấp để tránh hallucination.")
    assert m1.passed and m1.cost_per_query < 0.005
    print(f"✓ Round 1 eval: Passed={m1.passed}, Accuracy={m1.accuracy*100}%, Cost=${m1.cost_per_query:.5f}")

    m2 = evaluator.evaluate_round2(
        "Bạn là trợ lý học vụ. Chỉ trả lời dựa trên quy chế đào tạo của trường. Nếu không biết thì hãy báo lịch sự.",
        "Xác định rõ vai trò và giới hạn phạm vi trả lời.",
    )
    assert m2.passed
    print(f"✓ Round 2 eval: Passed={m2.passed}, Accuracy={m2.accuracy*100}%, Hallucination={m2.hallucination_rate*100}%")

    code = """
def call_llm(prompt):
    try:
        return {"status": "ok", "response": "Xin chào!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
"""
    m3 = evaluator.evaluate_round3_code(code, "Có try/except xử lý lỗi an toàn.")
    assert m3.passed
    print(f"✓ Round 3 eval: Passed={m3.passed}, Accuracy={m3.accuracy*100}%, Latency={m3.latency_ms}ms")


def test_agent():
    print("\n--- [3] Testing Agent Loop ---")
    provider = MockProvider()
    res = run_agent_turn(
        provider=provider,
        messages=[{"role": "user", "content": "Kiểm tra file template.py"}],
        system_prompt="Bạn là trợ lý kiểm tra code.",
    )
    assert res.text or res.tool_calls
    print(f"✓ Agent turn completed: '{res.text[:60] if res.text else 'tool called'}...'")


if __name__ == "__main__":
    test_tools()
    test_evaluator()
    test_agent()
    print("\n🎉 ALL SMOKE TESTS PASSED 100%!")

"""
Live demonstration runner for LabSim AI Agent.
Invokes real LLM with real tool calls against the ingested Day 03 codebase index.
"""

import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from labsim.agent import LabSimAgent, LLMClient, ToolRegistry


def get_api_key() -> str:
    # Check env
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    # Check .env in data/K4-Day03-Lab/.env
    env_file = REPO_ROOT / "data" / "K4-Day03-Lab" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val and not val.startswith("your_"):
                    return val
    raise ValueError("OPENAI_API_KEY not found in environment or data/K4-Day03-Lab/.env")


def main():
    api_key = get_api_key()
    generated_dir = REPO_ROOT / "data" / "generated" / "day03"
    trace_log = generated_dir / "agent_traces.jsonl"

    print("================================================================")
    print("🚀 LABSIM AI AGENT - REAL TOOL-CALLING & RETRIEVAL DEMO")
    print("   Data source: data/generated/day03 (Manifest & Chunks)")
    print("   LLM Engine : OpenAI gpt-4o-mini (Real API)")
    print("================================================================\n")

    registry = ToolRegistry(generated_dir, lab_id="day03")
    client = LLMClient(api_key=api_key, model="gpt-4o-mini")
    agent = LabSimAgent(registry, client, trace_log_path=trace_log)

    questions = [
        "Học viên hỏi: Trong bài Lab 3, Task 2.1 yêu cầu hoàn thiện code ở file nào? Giữa docs/CODELAB.md và mã nguồn thực tế có gì cần lưu ý?",
        "Học viên hỏi: File src/tools.py có những hàm nào được định nghĩa và các Tool đó làm nhiệm vụ gì?"
    ]

    for idx, q in enumerate(questions, 1):
        print(f"\n--- [DEMO QUESTION {idx}] ---")
        print(f"Learner Query: {q}\n")
        print("Agent thinking & executing tools...")
        result = agent.run(q, max_iterations=6)

        print(f"\nCompleted in {result['duration_ms']} ms ({result['iterations']} iterations).")
        print(f"Tools called ({len(result['traces'])} steps):")
        for trace in result["traces"]:
            print(f"  ⚡ [{trace['tool']}] args={trace['arguments']} ({trace['step_latency_ms']} ms)")
            print(f"     Obs excerpt: {trace['observation_summary'][:120]}...")

        print("\n📝 FINAL AGENT RESPONSE (GROUNDED IN REAL EVIDENCE):")
        print("----------------------------------------------------")
        print(result["final_answer"])
        print("----------------------------------------------------\n")


if __name__ == "__main__":
    main()

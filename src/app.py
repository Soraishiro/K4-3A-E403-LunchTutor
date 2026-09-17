"""
LabPath / LunchTutor — Unified Application Entrypoint

Supports 3 execution modes:
1. Terminal CLI (default):
   python -m src.app
   python src/app.py

2. Web Server Mode:
   python src/app.py --web [--port 8000]

3. Self-Test / Smoke Test Mode:
   python src/app.py --test
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# Ensure UTF-8 output on Windows consoles
for stream in (sys.stdout, sys.stderr):
    if stream and hasattr(stream, "reconfigure") and (not stream.encoding or stream.encoding.lower() != "utf-8"):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.engine import (
    DAY01_SCENARIO,
    EvalMetrics,
    HybridEvaluator,
    MockProvider,
    RoundDef,
    Scenario,
    SimulationMemory,
    get_provider,
    list_files,
    read_file,
    run_agent_turn,
    search_code,
    get_file_summary,
    search_transcript,
    get_misconceptions,
    MENTOR_SYSTEM_PROMPT,
    PAIRPAL_SYSTEM_PROMPT,
)


# ---------------------------------------------------------------------------
# Terminal CLI Runner
# ---------------------------------------------------------------------------
class TerminalCLI:
    def __init__(self, provider_name: str = "mock"):
        self.provider = get_provider(provider_name)
        self.evaluator = HybridEvaluator(self.provider)
        self.scenario: Scenario = DAY01_SCENARIO
        self.memory = SimulationMemory()
        self.current_round_idx: int = 0

    def print_box(self, title: str, content: str):
        print(f"\n┌── [ {title} ] " + "─" * max(0, 60 - len(title)))
        for line in content.splitlines():
            print(f"│  {line}")
        print("└" + "─" * 70)

    def start(self):
        print("\n" + "=" * 75)
        print(f"  AI20K LABPATH SIMULATOR · {self.scenario.title}")
        print("=" * 75)
        print(self.scenario.briefing)
        print("\n🎯 Mục tiêu cần đạt:")
        for i, obj in enumerate(self.scenario.objectives, 1):
            print(f"  {i}. {obj}")

        print("\n💡 Các lệnh hỗ trợ:")
        print("  • /mentor <câu hỏi>      : Hỏi Trợ giảng Socratic (gợi ý tự tư duy)")
        print("  • /pairpal <giải thích>  : Giảng giải cho bạn học PairPal (Protégé Effect)")
        print("  • /tools <lệnh> <args>   : Dùng tools kiểm tra codebase (list_files, read_file, search_code)")
        print("  • /submit                : Nộp quyết định cho vòng hiện tại (A, B, C hoặc chi tiết)")
        print("  • /status                : Xem lại tiến độ và kết quả")
        print("  • /quit                  : Thoát\n")

        while self.current_round_idx < len(self.scenario.rounds):
            self.run_round()

        self.debrief()

    def run_round(self):
        round_def: RoundDef = self.scenario.rounds[self.current_round_idx]
        print("\n" + "-" * 75)
        print(f"👉 VÒNG {round_def.number}: {round_def.title}")
        print("-" * 75)
        print(f"Mô tả: {round_def.description}")
        print(f"Mục tiêu: {round_def.objective}\n")

        if round_def.options:
            print("Lựa chọn gợi ý:")
            for opt in round_def.options:
                print(f"  [{opt['id']}] {opt['label']}")

        if round_def.pairpal_prompt:
            self.print_box("🧑‍🤝‍🧑 PairPal (Hỏi bạn)", round_def.pairpal_prompt)

        while True:
            try:
                raw = input(f"\n[Vòng {round_def.number} - Lệnh hoặc /submit]> ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nThoát phiên làm việc.")
                sys.exit(0)

            if not raw:
                continue

            if raw == "/quit":
                sys.exit(0)

            if raw == "/status":
                print(f"\nĐã hoàn thành {self.current_round_idx}/{len(self.scenario.rounds)} vòng.")
                print(f"Số lỗi ghi nhận: {len(self.memory.mistakes)}")
                continue

            if raw.startswith("/mentor"):
                q = raw[len("/mentor"):].strip()
                res = run_agent_turn(self.provider, [{"role": "user", "content": q}], system_prompt=MENTOR_SYSTEM_PROMPT)
                self.print_box("🎓 Socratic Mentor", res.text or "Hãy xem lại tài liệu bài học.")
                continue

            if raw.startswith("/pairpal"):
                exp = raw[len("/pairpal"):].strip()
                res = run_agent_turn(self.provider, [{"role": "user", "content": exp}], system_prompt=PAIRPAL_SYSTEM_PROMPT)
                self.print_box("🧑‍🤝‍🧑 PairPal", res.text or "Mình hiểu thêm một chút rồi, cảm ơn bạn!")
                continue

            if raw.startswith("/tools"):
                parts = raw.split()
                tool_name = parts[1] if len(parts) > 1 else "list_files"
                if tool_name == "list_files":
                    res = list_files("day01", max_depth=2)
                    print(f"Files ({res.get('count', 0)}):", [e['path'] for e in res.get('entries', [])[:8]])
                elif tool_name == "search_code":
                    kw = parts[2] if len(parts) > 2 else "temperature"
                    res = search_code("day01", query=kw)
                    print(f"Search '{kw}' ({res.get('match_count', 0)} matches):", res.get('results', [])[:3])
                continue

            if raw == "/submit" or raw.upper() in ("A", "B", "C"):
                choice = raw.upper() if raw.upper() in ("A", "B", "C") else input("Nhập lựa chọn của bạn (A/B/C hoặc nội dung): ").strip().upper()
                selected_opt = next((o for o in round_def.options if o["id"] == choice), None)
                is_correct = selected_opt["correct"] if selected_opt else (choice == "A")

                # Run evaluator
                if round_def.number == 1:
                    metrics = self.evaluator.evaluate_round1("gpt-4o-mini" if is_correct else "gpt-4o", 0.2 if is_correct else 1.0)
                elif round_def.number == 2:
                    metrics = self.evaluator.evaluate_round2("Bạn là trợ lý học vụ. Chỉ trả lời dựa trên tài liệu quy chế." if is_correct else "Trợ lý học vụ.")
                else:
                    metrics = self.evaluator.evaluate_round3_code("def call_api():\n    try:\n        return {'ok': True}\n    except Exception as e:\n        return {'error': str(e)}" if is_correct else "def call_api():\n    return client.call()")

                self.memory.record_decision(round_def.number, choice, is_correct, metrics.details[0] if metrics.details else "")
                self.memory.history_metrics.append(metrics)

                status_str = "✅ ĐẠT YÊU CẦU" if is_correct else "⚠️ CẦN RÚT KINH NGHIỆM"
                self.print_box(f"Đánh giá Vòng {round_def.number} · {status_str}", "\n".join(metrics.details))

                if is_correct:
                    self.current_round_idx += 1
                    break
                else:
                    print("Hãy điều chỉnh và nộp lại (/submit) hoặc nhờ /mentor trợ giúp.")

    def debrief(self):
        print("\n" + "=" * 75)
        print("🎉 HOÀN THÀNH TẤT CẢ CÁC VÒNG MÔ PHỎNG LABPATH!")
        print("=" * 75)
        for i, m in enumerate(self.memory.history_metrics, 1):
            print(f"Vòng {i}: Passed={m.passed}, Accuracy={m.accuracy*100:.0f}%, Cost=${m.cost_per_query:.5f}, Latency={m.latency_ms:.1f}ms")
        print("\nSession hoàn thành xuất sắc. Chúc mừng bạn!\n")


# ---------------------------------------------------------------------------
# Web Server Mode (Zero External Dependency)
# ---------------------------------------------------------------------------
class WebServerHandler(BaseHTTPRequestHandler):
    ui_path = PROJECT_ROOT / "src" / "ui.html"

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            if not self.ui_path.exists():
                self.send_error(404, "ui.html not found")
                return
            body = self.ui_path.read_text(encoding="utf-8").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/api/scenario":
            sc = DAY01_SCENARIO
            data = {
                "title": sc.title,
                "briefing": sc.briefing,
                "objectives": sc.objectives,
                "rounds": [
                    {"number": r.number, "title": r.title, "description": r.description, "options": r.options, "pairpal": r.pairpal_prompt}
                    for r in sc.rounds
                ],
            }
            self.json_resp(200, data)
            return

        self.send_error(404)

    def do_POST(self):
        if self.path == "/api/turn":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            action = payload.get("action", "")
            choice = payload.get("choice", "A").upper()

            evaluator = HybridEvaluator(MockProvider())
            if choice == "A":
                m = evaluator.evaluate_round1("gpt-4o-mini", 0.2)
                res = {"correct": True, "message": "Lựa chọn phù hợp: tối ưu chi phí & hạn chế hallucination.", "metrics": {"acc": m.accuracy, "cost": m.cost_per_query}}
            else:
                res = {"correct": False, "message": "Lựa chọn này có nguy cơ chi phí cao hoặc hallucination.", "metrics": {"acc": 0.5, "cost": 0.01}}
            self.json_resp(200, res)
            return

        self.send_error(404)

    def json_resp(self, code: int, data: dict[str, Any]):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any):
        return  # quiet logging


def run_web_server(port: int = 8000):
    server = ThreadingHTTPServer(("127.0.0.1", port), WebServerHandler)
    print(f"🚀 LabPath Web Server running at: http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
        print("\nWeb server stopped.")


# ---------------------------------------------------------------------------
# Self-Test Runner
# ---------------------------------------------------------------------------
def run_tests():
    print("=== [1] Running Engine Tools Test ===")
    r_list = list_files("day01", max_depth=2)
    assert r_list["status"] == "success"
    print(f"✓ list_files: {r_list['count']} files found.")

    r_read = read_file("day01", "template.py", start_line=1, end_line=15)
    assert r_read["status"] == "success"
    print(f"✓ read_file: read {r_read['total_lines']} total lines.")

    r_search = search_code("day01", "temperature")
    assert r_search["status"] == "success"
    print(f"✓ search_code: found {r_search['match_count']} matches.")

    r_ast = get_file_summary("day01", "template.py")
    assert r_ast["status"] == "success"
    print(f"✓ get_file_summary (AST): extracted {len(r_ast.get('definitions', []))} definitions.")

    r_misc = get_misconceptions("temperature")
    assert r_misc["status"] == "success" and r_misc["count"] > 0
    print(f"✓ get_misconceptions: found {r_misc['count']} items.")

    print("\n=== [2] Running Hybrid Evaluator Test ===")
    evaluator = HybridEvaluator(MockProvider())
    m1 = evaluator.evaluate_round1("gpt-4o-mini", 0.2)
    assert m1.passed and m1.cost_per_query < 0.005
    print(f"✓ Round 1: Passed={m1.passed}, Acc={m1.accuracy*100}%, Cost=${m1.cost_per_query:.5f}")

    m2 = evaluator.evaluate_round2("Bạn là trợ lý học vụ. Chỉ trả lời dựa trên tài liệu quy chế.")
    assert m2.passed
    print(f"✓ Round 2: Passed={m2.passed}, Acc={m2.accuracy*100}%, Hallucination={m2.hallucination_rate*100}%")

    code = "def call():\n    try:\n        return {'ok': True}\n    except Exception as e:\n        return {'err': str(e)}"
    m3 = evaluator.evaluate_round3_code(code)
    assert m3.passed
    print(f"✓ Round 3: Passed={m3.passed}, Latency={m3.latency_ms:.2f}ms")

    print("\n=== [3] Running Agent Turn Test ===")
    prov = MockProvider()
    res = run_agent_turn(prov, [{"role": "user", "content": "Kiểm tra file template.py"}])
    assert res.text or res.tool_calls
    print(f"✓ Agent turn completed: text length={len(res.text or '')}")

    print("\n🎉 ALL SELF-TESTS PASSED 100%!")


# ---------------------------------------------------------------------------
# Main CLI Entrypoint
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="LabPath / LunchTutor Unified Simulator")
    parser.add_argument("--web", action="store_true", help="Run web server serving ui.html")
    parser.add_argument("--port", type=int, default=8000, help="Port for web server (default: 8000)")
    parser.add_argument("--test", action="store_true", help="Run full self-test suite")
    parser.add_argument("--provider", type=str, default="mock", help="Provider: mock, openai, gemini")
    args = parser.parse_args()

    if args.test:
        run_tests()
    elif args.web:
        run_web_server(port=args.port)
    else:
        cli = TerminalCLI(provider_name=args.provider)
        cli.start()


if __name__ == "__main__":
    main()

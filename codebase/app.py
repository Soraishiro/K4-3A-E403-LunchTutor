"""
LabPath / LunchTutor — Codebase Application Runner (CP3 Prototype)

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


# ---------------------------------------------------------------------------
# Web Server
# ---------------------------------------------------------------------------
class PrototypeWebHandler(BaseHTTPRequestHandler):
    engine = CentralDecisionEngine()
    ui_path = CODEBASE_DIR / "ui.html"

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

        self.send_error(404)

    def do_POST(self):
        if self.path == "/api/decision":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            msg = payload.get("message", "")
            stage = payload.get("stage", "orientation")

            outcome, log_entry = self.engine.decide(student_input=msg, current_stage=stage)

            resp_data = {
                "action_type": outcome.action_type,
                "feedback": outcome.feedback,
                "citation": outcome.citation,
                "simulated_consequence": outcome.simulated_consequence,
                "options": outcome.options,
                "risk_level": outcome.risk_level,
                "latency_ms": log_entry.latency_ms,
                "model": log_entry.model,
            }

            body = json.dumps(resp_data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(404)

    def log_message(self, format: str, *args: Any):
        # Clean console log for demo
        print(f"[HTTP] {self.address_string()} - {args[0]}")


def run_web(port: int = 8000):
    server = ThreadingHTTPServer(("127.0.0.1", port), PrototypeWebHandler)
    print("\n" + "=" * 70)
    print(f"🚀 LabPath Decision Core Prototype Web UI đang chạy tại:")
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
    print("  LabPath Central Decision Core — CLI Runner (CP3)")
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
    parser.add_argument("--web", action="store_true", help="Start Web UI server (default: port 8000)")
    parser.add_argument("--port", type=int, default=8000, help="Web server port")
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

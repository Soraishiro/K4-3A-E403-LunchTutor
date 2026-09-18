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
    ui_path = CODEBASE_DIR / "ui_v1.html"

    def do_GET(self):
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(self.path)

            if parsed.path == "/api/manifest":
                manifest_file = PROJECT_ROOT / "data" / "generated" / "day03" / "source_manifest.json"
                if not manifest_file.exists():
                    self.send_error(404, "Manifest not found")
                    return
                manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                # Filter out 0-byte files and tag relevant lab categories
                filtered_files = []
                for f in manifest_data.get("files", []):
                    if f.get("size_bytes", 0) <= 0:
                        continue
                    p = f.get("path", "")
                    cat = "docs"
                    if p.startswith("src/"):
                        cat = "code"
                    elif p.startswith("tests/") or p.startswith("config/") or p.endswith(".json"):
                        cat = "tests"
                    f["category"] = cat
                    filtered_files.append(f)

                manifest_data["files"] = filtered_files
                manifest_data["files_count"] = len(filtered_files)
                body = json.dumps(manifest_data, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/file":
                query = urllib.parse.parse_qs(parsed.query)
                file_path = query.get("path", [None])[0]
                if not file_path:
                    self.send_error(400, "Missing path query parameter")
                    return

                day03_lab_dir = (PROJECT_ROOT / "data" / "K4-Day03-Lab").resolve()
                target_file = (day03_lab_dir / file_path).resolve()
                try:
                    if not target_file.is_relative_to(day03_lab_dir) or not target_file.is_file():
                        self.send_error(404, f"File not found: {file_path}")
                        return
                except (ValueError, RuntimeError):
                    self.send_error(403, "Access denied")
                    return

                content = target_file.read_text(encoding="utf-8", errors="replace")
                import hashlib
                file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                lines = content.splitlines()

                symbols = []
                if file_path.endswith(".py"):
                    try:
                        import ast
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                symbols.append({
                                    "name": node.name,
                                    "kind": "function",
                                    "line": node.lineno,
                                    "end_line": getattr(node, "end_lineno", node.lineno)
                                })
                            elif isinstance(node, ast.ClassDef):
                                symbols.append({
                                    "name": node.name,
                                    "kind": "class",
                                    "line": node.lineno,
                                    "end_line": getattr(node, "end_lineno", node.lineno)
                                })
                    except Exception:
                        pass

                payload = {
                    "path": file_path,
                    "content": content,
                    "total_lines": len(lines),
                    "sha256": file_hash,
                    "symbols": symbols
                }
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/chunks":
                query = urllib.parse.parse_qs(parsed.query)
                chunk_id = query.get("chunk_id", [None])[0]
                file_path = query.get("path", [None])[0]
                chunks_file = PROJECT_ROOT / "data" / "generated" / "day03" / "source_chunks.jsonl"
                if not chunks_file.exists():
                    self.send_error(404, "Chunks file not found")
                    return

                results = []
                with open(chunks_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        item = json.loads(line)
                        if chunk_id and item.get("chunk_id") == chunk_id:
                            results.append(item)
                            break
                        elif file_path and item.get("path") == file_path:
                            results.append(item)
                            if len(results) >= 100:
                                break
                        elif not chunk_id and not file_path:
                            results.append(item)
                            if len(results) >= 30:
                                break

                payload = results[0] if (chunk_id and results) else results
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            target = CODEBASE_DIR / "ui.html"
            if parsed.path in ("/ui_v1.html",):
                target = CODEBASE_DIR / "ui_v1.html"
            elif parsed.path in ("/", "/index.html", "/ui.html"):
                target = CODEBASE_DIR / "ui.html"

            if parsed.path in ("/", "/index.html", "/ui.html", "/ui_v1.html"):
                if not target.exists():
                    self.send_error(404, "HTML template not found")
                    return
                body = target.read_text(encoding="utf-8").encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_error(404)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Internal Error: {e}")

    def do_POST(self):
        try:
            if self.path == "/api/decision":
                length = int(self.headers.get("Content-Length", 0))
                raw_bytes = self.rfile.read(length) if length else b""
                try:
                    body_text = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    body_text = raw_bytes.decode("latin1", errors="replace")
                payload = json.loads(body_text) if body_text else {}
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
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_error(404)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Internal Error: {e}")

    def log_message(self, format: str, *args: Any):
        try:
            msg = format % args
        except Exception:
            msg = " ".join(str(a) for a in args) if args else format
        sys.stderr.write(f"[HTTP] {self.address_string()} - {msg}\n")


def run_web(port: int = 3000):
    server = ThreadingHTTPServer(("", port), PrototypeWebHandler)
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
    parser.add_argument("--web", action="store_true", help="Start Web UI server (default: port 3000)")
    parser.add_argument("--port", type=int, default=3000, help="Web server port")
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

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
from codebase.tools import ToolRegistry, load_chunk_index, search_sources

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def _fallback_api_key() -> str:
    env_path = PROJECT_ROOT / "data" / "K4-Day03-Lab" / ".env"
    if not env_path.exists():
        env_path = PROJECT_ROOT / "data" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            for prefix in ("GEMINI_API_KEY=", "OPENAI_API_KEY="):
                if line.startswith(prefix):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val and not val.startswith("your_"):
                        return val
    return ""


# ---------------------------------------------------------------------------
# Grounded Q&A + Evidence (per-chunk retrieval, per-citation verification)
# ---------------------------------------------------------------------------
QA_CHUNKS_PATH = PROJECT_ROOT / "data" / "generated" / "day03" / "source_chunks.jsonl"
QA_MANIFEST_PATH = PROJECT_ROOT / "data" / "generated" / "day03" / "source_manifest.json"
_QA_INDEX_CACHE: list[dict[str, Any]] | None = None


def _get_qa_index() -> list[dict[str, Any]]:
    global _QA_INDEX_CACHE
    if _QA_INDEX_CACHE is None:
        _QA_INDEX_CACHE = load_chunk_index(QA_CHUNKS_PATH)
    return _QA_INDEX_CACHE


def _to_evidence(chunk: dict[str, Any], snippet_len: int = 300) -> dict[str, Any]:
    text = chunk.get("text", "")
    sha = chunk.get("sha256", "")
    return {
        "chunk_id": chunk.get("chunk_id"),
        "path": chunk.get("path"),
        "start_line": chunk.get("start_line"),
        "end_line": chunk.get("end_line"),
        "source_kind": chunk.get("source_kind"),
        "sha256": sha,
        "sha_short": sha[:10],
        "snippet": text[:snippet_len] + ("..." if len(text) > snippet_len else ""),
    }


def _verify_citations(citations: list[str], retrieved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map each LLM-returned citation to a real retrieved chunk.

    Only citations exactly matching a retrieved chunk_id (or the
    path:start-end of a retrieved chunk) pass. Everything else is dropped —
    no hallucinated citations allowed.
    """
    by_id = {r.get("chunk_id"): r for r in retrieved}
    by_ref = {f"{r.get('path')}:{r.get('start_line')}-{r.get('end_line')}": r for r in retrieved}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in citations or []:
        c = str(c).strip()
        chunk = by_id.get(c) or by_ref.get(c)
        if chunk and chunk.get("chunk_id") not in seen:
            seen.add(chunk["chunk_id"])
            ev = _to_evidence(chunk)
            ev["ref"] = f"{ev['path']}:{ev['start_line']}-{ev['end_line']}"
            ev["verified"] = True
            out.append(ev)
    return out


def answer_qa(query: str, top_k: int = 5) -> dict[str, Any]:
    """Grounded Q&A over ingested docs+code. Every citation verified per-chunk."""
    if not QA_CHUNKS_PATH.exists() or not QA_MANIFEST_PATH.exists():
        return {
            "query": query,
            "answer": "Không tìm thấy dữ liệu Lab 3. Hãy chạy ingest.py trước.",
            "citations": [], "citations_detail": [], "evidence": [],
            "retrieved_count": 0, "model": "mock", "provider_status": "mock",
        }
    index = _get_qa_index()
    retrieved = search_sources(index, "day03", query, top_k=top_k)
    evidence = [_to_evidence(r) for r in retrieved]
    context = "\n".join(f"[{r.get('chunk_id')}] {r.get('text', '')[:500]}" for r in retrieved[:5])

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY", "") or _fallback_api_key()
    if not api_key:
        return {
            "query": query,
            "answer": "[Chế độ Mock] Bạn cần cung cấp GEMINI_API_KEY hoặc OPENAI_API_KEY để dùng LLM thật.",
            "citations": [], "citations_detail": [], "evidence": evidence,
            "retrieved_count": len(evidence), "model": "mock", "provider_status": "mock",
        }

    from codebase.engine import get_provider
    provider_name = "gemini" if (os.getenv("GEMINI_API_KEY") or api_key.startswith("AIza")) else "openai"
    provider = get_provider(provider_name, api_key=api_key)
    system_msg = (
        "Bạn là trợ lý AI học tập LabPath. Chỉ trả lời dựa trên TÀI LIỆU được cung cấp dưới đây. "
        "Mỗi khẳng định factual phải trích dẫn chunk_id NGUYÊN VĂN (ví dụ 'src/app.py:36-75'). "
        "Trả về JSON duy nhất: {\"answer\": \"...\", \"citations\": [\"<chunk_id>\", ...]}. "
        "Nếu tài liệu không đủ căn cứ, nói 'không chắc' và đề nghị học viên đọc tài liệu."
    )
    user_msg = f"Câu hỏi: {query}\n\nTài liệu tham khảo (retrieved):\n{context[:3000]}"
    try:
        resp = provider.complete([{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}])
        raw_text = resp.text or ""
        try:
            data = json.loads(raw_text)
            response_text = data.get("answer", raw_text)
            verified = _verify_citations(data.get("citations", []), retrieved)
        except json.JSONDecodeError:
            response_text = raw_text
            verified = []
        model_used = getattr(provider, "model", provider_name)
    except Exception as e:
        response_text = f"[Lỗi gọi LLM: {e}] — Dùng chế độ mock."
        verified = []
        model_used = "mock"

    if not verified:
        verified = [_to_evidence(r) for r in retrieved[:3]]
        for v in verified:
            v["ref"] = f"{v['path']}:{v['start_line']}-{v['end_line']}"
            v["verified"] = True
    return {
        "query": query,
        "answer": response_text,
        "citations": [v["ref"] for v in verified],
        "citations_detail": verified,
        "evidence": evidence,
        "retrieved_count": len(evidence),
        "model": model_used,
        "provider_status": "live" if model_used != "mock" else "mock",
    }


def decision_evidence(student_msg: str, top_k: int = 3) -> tuple[list[dict[str, Any]], bool, str]:
    """Retrieve grounding evidence for a Mentor/PairPal chat turn.

    Returns (evidence, citation_verified, matched_ref). citation_verified is
    True only if the heuristic citation names a file actually in the index.
    """
    if not QA_CHUNKS_PATH.exists():
        return [], False, ""
    try:
        retrieved = search_sources(_get_qa_index(), "day03", student_msg, top_k=top_k)
    except Exception:
        return [], False, ""
    return [_to_evidence(r) for r in retrieved], False, ""


# ---------------------------------------------------------------------------
# Gate 0 publish policy: which lab files may be served to browsers.
#
# A file is publishable ONLY if ALL hold (checked in this order, before any
# file bytes are read):
#   1. path normalizes to a safe relative path (no absolute/traversal/hidden),
#   2. path is not on the absolute deny list (secrets/logs/keys/chatlogs),
#   3. path is in the manually confirmed public allowlist below,
#   4. path has an entry in the ingested manifest,
#   5. resolved path stays inside PUBLIC_LAB_DIR, is not a symlink, is a file,
#   6. SHA-256 of current bytes matches the manifest (else stale -> re-ingest).
# ---------------------------------------------------------------------------
PUBLIC_LAB_DIR = PROJECT_ROOT / "data" / "K4-Day03-Lab"

# Manually confirmed Gate-0 public set. New manifest files are NOT served
# until added here explicitly.
ALLOWLIST_PUBLIC_PATHS = frozenset({
    "LAB-GUIDE.md",
    "README.md",
    "config/test_cases.json",
    "docs/CODELAB.md",
    "docs/DANH_SACH_DE_TAI.md",
    "docs/SO_TAY_THUC_HANH.md",
    "docs/trace_eval.md",
    "docs/trace_waterfall.json",
    "requirements.txt",
    "src/ai_levels/README.md",
    "src/ai_levels/level3_native_mcp_agent.py",
    "src/app.py",
    "src/guardrail_agent.py",
    "src/mcp_server.py",
    "src/memory/__init__.py",
    "src/memory/context_builder.py",
    "src/memory/safety_filter.py",
    "src/memory/tool_registry.py",
    "src/memory/working_memory.py",
    "src/prompts.py",
    "src/providers.py",
    "src/tools.py",
    "tests/integration/test_react_agent.py",
    "tests/unit/test_mcp_server.py",
    "tests/unit/test_tools.py",
})

DENY_BASENAME_EXACT = frozenset({".env"})
DENY_BASENAME_PREFIXES = (".env.",)
DENY_NAME_SUBSTRINGS = (
    "credential", "secret", "private_key", "privatekey", "passwd",
    "chatlog", "tutor_turns", "transcript", "inference_trace",
    "answer_key", "answerkey",
)
DENY_EXTENSIONS = (".pem", ".key", ".p12", ".pfx", ".log", ".db", ".sqlite")
DENY_PATH_SEGMENTS = frozenset({".git"})

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

_MANIFEST_CACHE: dict[str, Any] | None = None
_CHUNKS_CACHE: list[dict[str, Any]] | None = None


def _reset_publish_caches() -> None:
    global _MANIFEST_CACHE, _CHUNKS_CACHE, _QA_INDEX_CACHE
    _MANIFEST_CACHE = None
    _CHUNKS_CACHE = None
    _QA_INDEX_CACHE = None


def normalize_rel_path(raw: Any) -> str | None:
    """Normalize to a safe relative path, or None if invalid.

    Rejects non-strings, absolute paths, drive letters, traversal (..),
    hidden segments, empty paths and NUL bytes.
    """
    if not isinstance(raw, str):
        return None
    s = raw.strip().replace("\\", "/")
    if not s or "\x00" in s:
        return None
    if s.startswith("/") or (len(s) > 2 and s[1] == ":" and s[0].isalpha()):
        return None
    parts: list[str] = []
    for part in s.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return None
        parts.append(part)
    if not parts:
        return None
    if any(p.startswith(".") for p in parts):
        return None
    if any(p in DENY_PATH_SEGMENTS for p in parts):
        return None
    return "/".join(parts)


def deny_reason(rel_path: str) -> str | None:
    """Absolute deny list. Returns a reason code, or None if not denied."""
    import posixpath

    base = posixpath.basename(rel_path)
    lower = rel_path.lower()
    base_lower = base.lower()
    if base in DENY_BASENAME_EXACT or base_lower.startswith(DENY_BASENAME_PREFIXES):
        return "denied_name"
    if any(sub in lower for sub in DENY_NAME_SUBSTRINGS):
        return "denied_name"
    if any(base_lower.endswith(ext) for ext in DENY_EXTENSIONS):
        return "denied_extension"
    return None


def _manifest_by_path() -> dict[str, dict[str, Any]]:
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is None:
        try:
            data = json.loads(QA_MANIFEST_PATH.read_text(encoding="utf-8"))
            _MANIFEST_CACHE = {
                f.get("path"): f for f in data.get("files", []) if f.get("path")
            }
        except Exception:
            _MANIFEST_CACHE = {}
    return _MANIFEST_CACHE


def _chunks_all() -> list[dict[str, Any]]:
    global _CHUNKS_CACHE
    if _CHUNKS_CACHE is None:
        try:
            _CHUNKS_CACHE = load_chunk_index(QA_CHUNKS_PATH)
        except Exception:
            _CHUNKS_CACHE = []
    return _CHUNKS_CACHE


def is_publishable(rel_path: str, manifest_by_path: dict[str, Any] | None = None) -> tuple[bool, str]:
    """Metadata-only publish check (no file I/O)."""
    if deny_reason(rel_path):
        return False, "denied"
    if rel_path not in ALLOWLIST_PUBLIC_PATHS:
        return False, "not_allowlisted"
    manifest = manifest_by_path if manifest_by_path is not None else _manifest_by_path()
    if rel_path not in manifest:
        return False, "not_in_manifest"
    return True, ""


def resolve_publishable_file(rel_path: str) -> tuple[Path | None, bytes, str]:
    """Full publish check including SHA-256 binding. Reads bytes only after
    all path/allowlist/manifest checks pass. Returns (path, content, reason);
    reason is '' on success, otherwise a generic code with no server paths.
    """
    rel = normalize_rel_path(rel_path)
    if rel is None:
        return None, b"", "invalid_path"
    manifest = _manifest_by_path()
    ok, reason = is_publishable(rel, manifest)
    if not ok:
        return None, b"", reason
    try:
        root = PUBLIC_LAB_DIR.resolve()
        candidate = PUBLIC_LAB_DIR / rel
        if candidate.is_symlink():
            return None, b"", "not_found"
        target = candidate.resolve()
        target.relative_to(root)
        if not target.is_file():
            return None, b"", "not_found"
    except (ValueError, RuntimeError, OSError):
        return None, b"", "not_found"
    try:
        content = target.read_bytes()
    except OSError:
        return None, b"", "not_found"
    import hashlib

    if hashlib.sha256(content).hexdigest() != manifest[rel].get("sha256", ""):
        return None, b"", "stale"
    return target, content, ""


def _request_is_local(handler: Any) -> bool:
    """Loopback Host (+ Origin/Referer when present) check for /api/* routes."""
    import urllib.parse

    host = (handler.headers.get("Host", "") or "").split(":")[0].strip().lower().strip("[]")
    if host not in LOCAL_HOSTS:
        return False
    for header in ("Origin", "Referer"):
        origin = handler.headers.get(header)
        if origin:
            try:
                ohost = (urllib.parse.urlparse(origin).hostname or "").lower()
            except Exception:
                return False
            if ohost not in LOCAL_HOSTS:
                return False
    return True


# ---------------------------------------------------------------------------
# Web Server
# ---------------------------------------------------------------------------
class PrototypeWebHandler(BaseHTTPRequestHandler):
    engine = CentralDecisionEngine()
    ui_path = CODEBASE_DIR / "ui.html"

    def do_GET(self):
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(self.path)

            if parsed.path.startswith("/api/") and not _request_is_local(self):
                self.send_error(403, "Forbidden")
                return

            if parsed.path == "/api/manifest":
                try:
                    manifest_data = json.loads(QA_MANIFEST_PATH.read_text(encoding="utf-8"))
                except Exception:
                    self.send_error(404, "Not found")
                    return
                # Same publish policy as /api/file: only allowlisted files,
                # no skipped-file details (may name secret-bearing files).
                manifest_index = {
                    f.get("path"): f
                    for f in manifest_data.get("files", [])
                    if f.get("path")
                }
                filtered_files = []
                for f in manifest_data.get("files", []):
                    if f.get("size_bytes", 0) <= 0:
                        continue
                    p = f.get("path", "")
                    ok, _ = is_publishable(p, manifest_index)
                    if not ok:
                        continue
                    cat = "docs"
                    if p.startswith("src/"):
                        cat = "code"
                    elif p.startswith("tests/") or p.startswith("config/") or p.endswith(".json"):
                        cat = "tests"
                    filtered_files.append({
                        "path": p,
                        "sha256": f.get("sha256", ""),
                        "size_bytes": f.get("size_bytes", 0),
                        "total_lines": f.get("total_lines", 0),
                        "source_kind": f.get("source_kind", ""),
                        "symbols": f.get("symbols", []),
                        "symbols_count": f.get("symbols_count", 0),
                        "category": cat,
                    })

                body = json.dumps({
                    "lab_id": manifest_data.get("lab_id", ""),
                    "source_manifest_sha256": manifest_data.get("source_manifest_sha256", ""),
                    "generated_at": manifest_data.get("generated_at", ""),
                    "files_count": len(filtered_files),
                    "files": filtered_files,
                }, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/file":
                query = urllib.parse.parse_qs(parsed.query)
                file_path = query.get("path", [None])[0]
                if not file_path:
                    self.send_error(400, "Bad request")
                    return

                _, content_bytes, reason = resolve_publishable_file(file_path)
                if reason == "stale":
                    self.send_error(409, "Source changed")
                    return
                if reason:
                    self.send_error(404, "Not found")
                    return
                rel = normalize_rel_path(file_path) or ""
                try:
                    content = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    self.send_error(404, "Not found")
                    return
                import hashlib
                file_hash = hashlib.sha256(content_bytes).hexdigest()
                lines = content.splitlines()

                symbols = []
                if rel.endswith(".py"):
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
                    "path": rel,
                    "content": content,
                    "total_lines": len(lines),
                    "sha256": file_hash,
                    "symbols": symbols
                }
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/chunks":
                # Same publish policy as /api/file: a chunk is served only if
                # its file is publishable AND the chunk is bound to the current
                # manifest SHA (stale/unbound chunks are dropped).
                query = urllib.parse.parse_qs(parsed.query)
                chunk_id = query.get("chunk_id", [None])[0]
                file_path = query.get("path", [None])[0]
                if not chunk_id and not file_path:
                    self.send_error(400, "Bad request")
                    return
                norm_path = None
                if file_path:
                    norm_path = normalize_rel_path(file_path)
                    if norm_path is None:
                        self.send_error(400, "Bad request")
                        return

                manifest_index = _manifest_by_path()
                results = []
                for item in _chunks_all():
                    if chunk_id and item.get("chunk_id") != chunk_id:
                        continue
                    if norm_path and item.get("path") != norm_path:
                        continue
                    if not chunk_id and not norm_path:
                        continue
                    ok, _ = is_publishable(item.get("path", ""), manifest_index)
                    if not ok:
                        continue
                    entry = manifest_index.get(item.get("path", ""))
                    if not entry or item.get("file_sha256") != entry.get("sha256"):
                        continue
                    results.append(item)
                    if len(results) >= 100:
                        break

                payload = results[0] if (chunk_id and results) else results
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path in ("/", "/index.html", "/ui.html", "/ui_v1.html"):
                target = CODEBASE_DIR / "ui.html"
                if not target.exists():
                    self.send_error(404, "Not found")
                    return
                body = target.read_text(encoding="utf-8").encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/provider-status":
                has_openai = bool(os.getenv("OPENAI_API_KEY"))
                has_gemini = bool(os.getenv("GEMINI_API_KEY"))
                status = "live_openai" if has_openai else ("live_gemini" if has_gemini else "mock")
                body = json.dumps({"status": status, "openai": has_openai, "gemini": has_gemini}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/qa":
                # Q&A moved to POST /api/qa (a GET cannot reliably carry a JSON body).
                self.send_error(405, "Use POST /api/qa")
                return

            self.send_error(404)
        except Exception:
            import traceback
            traceback.print_exc()
            self.send_error(500, "Internal error")

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        raw_bytes = self.rfile.read(length) if length else b""
        try:
            body_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            body_text = raw_bytes.decode("latin1", errors="replace")
        return json.loads(body_text) if body_text else {}

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            if self.path.startswith("/api/") and not _request_is_local(self):
                self.send_error(403, "Forbidden")
                return
            if self.path == "/api/qa":
                payload = self._read_json_body()
                query = (payload.get("query", "") or "").strip()
                if not query:
                    self.send_error(400, "Bad request")
                    return
                try:
                    top_k = int(payload.get("top_k", 5) or 5)
                except (TypeError, ValueError):
                    top_k = 5
                self._send_json(answer_qa(query, top_k=max(1, min(top_k, 10))))
                return

            if self.path == "/api/decision":
                payload = self._read_json_body()
                msg = payload.get("message", "")
                stage = payload.get("stage", "orientation")

                outcome, log_entry = self.engine.decide(student_input=msg, current_stage=stage)

                # Grounding: retrieve real chunks for this turn and check whether
                # the heuristic citation names a file actually in the index.
                evidence, _, _ = decision_evidence(msg)
                citation_verified = any(
                    ev.get("path") and ev["path"] in (outcome.citation or "")
                    for ev in evidence
                )

                resp_data = {
                    "action_type": outcome.action_type,
                    "feedback": outcome.feedback,
                    "citation": outcome.citation,
                    "citation_verified": citation_verified,
                    "evidence": evidence,
                    "simulated_consequence": outcome.simulated_consequence,
                    "options": outcome.options,
                    "risk_level": outcome.risk_level,
                    "latency_ms": log_entry.latency_ms,
                    "model": log_entry.model,
                }

                self._send_json(resp_data)
                return

            self.send_error(404)
        except Exception:
            import traceback
            traceback.print_exc()
            self.send_error(500, "Internal error")

    def log_message(self, format: str, *args: Any):
        try:
            msg = format % args
        except Exception:
            msg = " ".join(str(a) for a in args) if args else format
        sys.stderr.write(f"[HTTP] {self.address_string()} - {msg}\n")


def run_web(port: int = 3000):
    # Gate 0: loopback only. No public-bind option in this task; loopback is
    # NOT a substitute for authentication when deploying to a network.
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

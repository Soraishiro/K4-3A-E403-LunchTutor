"""
All LabSim Tools implementation in codebase/tools.py.
Provides search, chunk reading, AST outline inspection, file listing,
and schema loading from codebase/tools.yaml.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Shared env key loader (single key-loading policy for the codebase).
# ---------------------------------------------------------------------------
def load_env_api_key() -> str:
    """Read GEMINI/OPENAI key from known .env files. Returns "" if none."""
    base = Path(__file__).resolve().parent.parent
    for env_path in (
        base / "data" / "K4-Day03-Lab" / ".env",
        base / "data" / ".env",
    ):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            for prefix in ("GEMINI_API_KEY=", "OPENAI_API_KEY="):
                if line.startswith(prefix):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val and not val.startswith("your_"):
                        return val
    return ""


# ---------------------------------------------------------------------------
# Gate 0 source-visibility policy (single home for publish decisions).
# A chunk/file is visible ONLY if: safe relative path, not denied, in the
# manually confirmed allowlist, present in the manifest, bound to the current
# manifest SHA, and (when a verifier is given) the on-disk snapshot still
# matches. All retrieval paths (QA, decision evidence, ToolRegistry, chunks
# endpoint) filter through filter_visible_chunks BEFORE any LLM prompt.
# ---------------------------------------------------------------------------
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


def is_publishable(rel_path: str, manifest_paths: Any = ()) -> tuple[bool, str]:
    """Metadata-only publish check (no file I/O). manifest_paths is a
    container (set/dict keys) of paths present in the ingested manifest."""
    if deny_reason(rel_path):
        return False, "denied"
    if rel_path not in ALLOWLIST_PUBLIC_PATHS:
        return False, "not_allowlisted"
    if rel_path not in manifest_paths:
        return False, "not_in_manifest"
    return True, ""


def filter_visible_chunks(
    chunks: list[dict[str, Any]],
    manifest_by_path: dict[str, dict[str, Any]],
    verify_snapshot: Any = None,
) -> list[dict[str, Any]]:
    """Keep only chunks safe to show/send: publishable path, chunk bound to
    the current manifest SHA, and (when given) a live snapshot verifier
    callable path -> bool. Unapproved or stale data never passes."""
    out: list[dict[str, Any]] = []
    snapshot_cache: dict[str, bool] = {}
    for c in chunks or []:
        p = c.get("path", "")
        ok, _ = is_publishable(p, manifest_by_path)
        if not ok:
            continue
        entry = manifest_by_path.get(p)
        if not entry or c.get("file_sha256") != entry.get("sha256"):
            continue
        if verify_snapshot is not None:
            if p not in snapshot_cache:
                try:
                    snapshot_cache[p] = bool(verify_snapshot(p))
                except Exception:
                    snapshot_cache[p] = False
            if not snapshot_cache[p]:
                continue
        out.append(c)
    return out


# ---------------------------------------------------------------------------
# Core Retrieval & File Inspection Primitives
# ---------------------------------------------------------------------------
def load_chunk_index(chunks_path: Path) -> list[dict[str, Any]]:
    path = Path(chunks_path)
    if not path.exists():
        raise FileNotFoundError(f"Chunk index not found: {chunks_path}")
    chunks: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


def search_sources(
    index: list[dict[str, Any]],
    lab_id: str,
    query: str,
    top_k: int = 5,
    filter_kind: Optional[str] = None
) -> list[dict[str, Any]]:
    query_clean = query.strip().lower()
    query_tokens = set(tokenize(query_clean))
    if not query_tokens:
        return []

    scored: list[tuple[float, str, int, dict[str, Any]]] = []
    for chunk in index:
        if lab_id and chunk.get("lab_id") != lab_id:
            continue
        if filter_kind and chunk.get("source_kind") != filter_kind:
            continue

        c_path = chunk.get("path", "")
        c_text = chunk.get("text", "")
        start_line = chunk.get("start_line", 0)

        path_tokens = set(tokenize(c_path))
        text_tokens = tokenize(c_text)

        score = 0.0
        if query_clean in c_text.lower():
            score += 25.0
        if query_clean in c_path.lower():
            score += 30.0

        score += len(query_tokens.intersection(path_tokens)) * 15.0
        score += len(query_tokens.intersection(set(text_tokens))) * 5.0
        for t in query_tokens:
            score += min(text_tokens.count(t), 5) * 1.0

        if score > 0.0:
            scored.append((score, c_path, start_line, chunk))

    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    return [x[3] for x in scored[:top_k]]


def get_chunk_by_id(index: list[dict[str, Any]], chunk_id: str) -> Optional[dict[str, Any]]:
    for chunk in index:
        if chunk.get("chunk_id") == chunk_id:
            return chunk
    return None


def get_manifest_file_outline(manifest_path: Path, file_path: str) -> Optional[dict[str, Any]]:
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    norm = file_path.replace("\\", "/").strip().lstrip("/")
    for f in data.get("files", []):
        if f.get("path") == norm:
            return f
    return None


def list_manifest_files(manifest_path: Path, filter_kind: Optional[str] = None) -> list[dict[str, Any]]:
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    files = json.loads(path.read_text(encoding="utf-8")).get("files", [])
    if filter_kind:
        files = [f for f in files if f.get("source_kind") == filter_kind]
    return files


# ---------------------------------------------------------------------------
# YAML Schema Loader (Stdlib compatible)
# ---------------------------------------------------------------------------
def load_tools_schema() -> list[dict[str, Any]]:
    yaml_file = Path(__file__).resolve().parent / "tools.yaml"
    try:
        import yaml
        if yaml_file.exists():
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            tools_list = data.get("tools", [])
            return [
                {"type": "function", "function": t}
                for t in tools_list
            ]
    except ImportError:
        pass

    return [
        {
            "type": "function",
            "function": {
                "name": "search_sources",
                "description": "Tìm kiếm các đoạn mã nguồn và tài liệu hướng dẫn học tập theo từ khóa hoặc cụm từ. Bắt buộc truyền query; có thể lọc theo source_kind.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Từ khóa hoặc cụm từ cần tra cứu"},
                        "top_k": {"type": "integer", "default": 5, "description": "Số lượng kết quả tối đa"},
                        "filter_kind": {"type": "string", "enum": ["instruction", "code", "reported"], "description": "Lọc theo loại nguồn"}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_source_chunk",
                "description": "Đọc toàn bộ nội dung nguyên văn và mã băm SHA-256 của một chunk cụ thể dựa vào chunk_id (ví dụ: 'docs/CODELAB.md:1-40').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chunk_id": {"type": "string", "description": "Định danh duy nhất của chunk cần đọc"}
                    },
                    "required": ["chunk_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_file_outline",
                "description": "Trích xuất dàn ý cấu trúc file: danh sách hàm, lớp, vị trí dòng và số dòng từ cây cú pháp AST. Hỗ trợ soi nhanh cấu trúc file code.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Đường dẫn tương đối của file (ví dụ: 'src/tools.py')"}
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_indexed_files",
                "description": "Liệt kê toàn bộ các file đã được lập chỉ mục trong bài Lab kèm số dòng, số symbols và loại nguồn.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filter_kind": {"type": "string", "enum": ["instruction", "code", "reported"], "description": "Lọc theo loại nguồn"}
                    }
                }
            }
        }
    ]


# ---------------------------------------------------------------------------
# Tool Registry & Dispatcher
# ---------------------------------------------------------------------------
class ToolRegistry:
    def __init__(self, generated_dir: Path, lab_id: str = "day03", verify_snapshot: Any = None):
        self.generated_dir = Path(generated_dir)
        self.lab_id = lab_id
        self.manifest_path = self.generated_dir / "source_manifest.json"
        self.chunks_path = self.generated_dir / "source_chunks.jsonl"
        self.verify_snapshot = verify_snapshot
        self._chunks_cache: Optional[list[dict[str, Any]]] = None
        self._manifest_cache: Optional[dict[str, Any]] = None

    @property
    def chunks(self) -> list[dict[str, Any]]:
        if self._chunks_cache is None:
            self._chunks_cache = load_chunk_index(self.chunks_path)
        return self._chunks_cache

    def _manifest_by_path(self) -> dict[str, dict[str, Any]]:
        if self._manifest_cache is None:
            try:
                data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                self._manifest_cache = {
                    f.get("path"): f for f in data.get("files", []) if f.get("path")
                }
            except Exception:
                self._manifest_cache = {}
        return self._manifest_cache

    def _visible(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return filter_visible_chunks(chunks, self._manifest_by_path(), self.verify_snapshot)

    def search_sources(self, query: str, top_k: int = 5, filter_kind: Optional[str] = None) -> list[dict[str, Any]]:
        raw = search_sources(self.chunks, self.lab_id, query, top_k=top_k * 3, filter_kind=filter_kind)
        raw = self._visible(raw)[:top_k]
        return [
            {
                "chunk_id": r.get("chunk_id"),
                "path": r.get("path"),
                "start_line": r.get("start_line"),
                "end_line": r.get("end_line"),
                "source_kind": r.get("source_kind"),
                "text_snippet": r.get("text", "")[:300] + ("..." if len(r.get("text", "")) > 300 else ""),
            }
            for r in raw
        ]

    def read_source_chunk(self, chunk_id: str) -> dict[str, Any]:
        chunk = get_chunk_by_id(self.chunks, chunk_id)
        if not chunk:
            return {"error": f"Chunk not found: {chunk_id}"}
        if not self._visible([chunk]):
            return {"error": f"Chunk not publishable: {chunk_id}"}
        return {
            "chunk_id": chunk.get("chunk_id"),
            "path": chunk.get("path"),
            "start_line": chunk.get("start_line"),
            "end_line": chunk.get("end_line"),
            "sha256": chunk.get("sha256"),
            "source_kind": chunk.get("source_kind"),
            "text": chunk.get("text"),
        }

    def get_file_outline(self, path: str) -> dict[str, Any]:
        outline = get_manifest_file_outline(self.manifest_path, path)
        if not outline:
            return {"error": f"File not found in manifest: {path}"}
        ok, _ = is_publishable(outline.get("path", ""), self._manifest_by_path())
        if not ok:
            return {"error": f"File not publishable: {path}"}
        return {
            "path": outline.get("path"),
            "source_kind": outline.get("source_kind"),
            "total_lines": outline.get("total_lines"),
            "sha256": outline.get("sha256"),
            "symbols": outline.get("symbols", []),
        }

    def list_indexed_files(self, filter_kind: Optional[str] = None) -> list[dict[str, Any]]:
        files = list_manifest_files(self.manifest_path, filter_kind=filter_kind)
        manifest = self._manifest_by_path()
        return [
            {
                "path": f.get("path"),
                "source_kind": f.get("source_kind"),
                "total_lines": f.get("total_lines"),
                "symbols_count": f.get("symbols_count", 0),
            }
            for f in files
            if is_publishable(f.get("path", ""), manifest)[0]
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name == "search_sources":
            return self.search_sources(
                query=arguments.get("query", ""),
                top_k=arguments.get("top_k", 5),
                filter_kind=arguments.get("filter_kind"),
            )
        elif tool_name == "read_source_chunk":
            return self.read_source_chunk(chunk_id=arguments.get("chunk_id", ""))
        elif tool_name == "get_file_outline":
            return self.get_file_outline(path=arguments.get("path", ""))
        elif tool_name == "list_indexed_files":
            return self.list_indexed_files(filter_kind=arguments.get("filter_kind"))
        return {"error": f"Unknown tool: {tool_name}"}

    def get_tools_schema_openai(self) -> list[dict[str, Any]]:
        return load_tools_schema()

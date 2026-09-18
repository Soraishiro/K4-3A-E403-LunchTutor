"""
All LabSim Tools implementation in a single unified module.
Provides search, chunk reading, AST outline inspection, file listing,
and schema loading from tools.yaml.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


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
    """
    Load tool schemas. If PyYAML is available, load from tools.yaml;
    otherwise use the standard declarative specification.
    """
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

    # Standard declarative schema mirroring tools.yaml
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
    def __init__(self, generated_dir: Path, lab_id: str = "day03"):
        self.generated_dir = Path(generated_dir)
        self.lab_id = lab_id
        self.manifest_path = self.generated_dir / "source_manifest.json"
        self.chunks_path = self.generated_dir / "source_chunks.jsonl"
        self._chunks_cache: Optional[list[dict[str, Any]]] = None

    @property
    def chunks(self) -> list[dict[str, Any]]:
        if self._chunks_cache is None:
            self._chunks_cache = load_chunk_index(self.chunks_path)
        return self._chunks_cache

    def search_sources(self, query: str, top_k: int = 5, filter_kind: Optional[str] = None) -> list[dict[str, Any]]:
        raw = search_sources(self.chunks, self.lab_id, query, top_k=top_k, filter_kind=filter_kind)
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
        return {
            "path": outline.get("path"),
            "source_kind": outline.get("source_kind"),
            "total_lines": outline.get("total_lines"),
            "sha256": outline.get("sha256"),
            "symbols": outline.get("symbols", []),
        }

    def list_indexed_files(self, filter_kind: Optional[str] = None) -> list[dict[str, Any]]:
        files = list_manifest_files(self.manifest_path, filter_kind=filter_kind)
        return [
            {
                "path": f.get("path"),
                "source_kind": f.get("source_kind"),
                "total_lines": f.get("total_lines"),
                "symbols_count": f.get("symbols_count", 0),
            }
            for f in files
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

"""
Scoped lexical retrieval over chunk index and manifest inspection.
Provides read-only, deterministic evidence search for the AI Agent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, List, Optional


def load_chunk_index(chunks_path: Path) -> list[dict[str, Any]]:
    """Load pre-computed chunks from JSONL file."""
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
    """Extract lowercase alphanumeric tokens."""
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


def search_sources(
    index: list[dict[str, Any]],
    lab_id: str,
    query: str,
    top_k: int = 5,
    filter_kind: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    Deterministically search chunks using lexical token matching and phrase scoring.
    """
    query_clean = query.strip().lower()
    query_tokens = set(tokenize(query_clean))
    if not query_tokens:
        return []

    scored_results: list[tuple[float, str, int, dict[str, Any]]] = []

    for chunk in index:
        if lab_id and chunk.get("lab_id") != lab_id:
            continue
        if filter_kind and chunk.get("source_kind") != filter_kind:
            continue

        chunk_path = chunk.get("path", "")
        chunk_text = chunk.get("text", "")
        start_line = chunk.get("start_line", 0)

        path_tokens = set(tokenize(chunk_path))
        text_tokens = tokenize(chunk_text)
        text_token_set = set(text_tokens)

        score = 0.0

        # Exact phrase match bonus
        if query_clean in chunk_text.lower():
            score += 25.0
        if query_clean in chunk_path.lower():
            score += 30.0

        # Token overlap in path
        path_matches = query_tokens.intersection(path_tokens)
        score += len(path_matches) * 15.0

        # Token overlap in text
        text_matches = query_tokens.intersection(text_token_set)
        score += len(text_matches) * 5.0

        # Frequency bonus (up to 5 occurrences)
        for t in query_tokens:
            count = text_tokens.count(t)
            score += min(count, 5) * 1.0

        if score > 0.0:
            # Deterministic tie-breaker: (-score, path, start_line)
            scored_results.append((score, chunk_path, start_line, chunk))

    scored_results.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [item[3] for item in scored_results[:top_k]]


def get_chunk_by_id(index: list[dict[str, Any]], chunk_id: str) -> Optional[dict[str, Any]]:
    """Fetch exact chunk by unique chunk_id."""
    for chunk in index:
        if chunk.get("chunk_id") == chunk_id:
            return chunk
    return None


def get_manifest_file_outline(manifest_path: Path, file_path: str) -> Optional[dict[str, Any]]:
    """Look up file outline (symbols, total lines, sha256) from source_manifest.json."""
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    norm_path = file_path.replace("\\", "/").strip().lstrip("/")
    for f in data.get("files", []):
        if f.get("path") == norm_path:
            return f
    return None


def list_manifest_files(manifest_path: Path, filter_kind: Optional[str] = None) -> list[dict[str, Any]]:
    """List indexed files from source_manifest.json."""
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    files = data.get("files", [])
    if filter_kind:
        files = [f for f in files if f.get("source_kind") == filter_kind]
    return files

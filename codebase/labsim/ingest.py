"""
Offline source ingestion with traceable provenance.
Scans source files, filters secrets/hidden files, computes deterministic SHA-256 hashes,
splits text into line-range chunks, and outputs manifest and JSONL artifacts.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Literal

ALLOWED_EXTENSIONS = {".md", ".txt", ".py", ".json", ".yaml", ".yml"}
MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1 MiB

SECRET_PATTERNS = [
    re.compile(r"(?:api[_-]?key|secret|password|bearer|private_key|token)\s*[:=]\s*['\"][A-Za-z0-9_\-\.]{12,}['\"]", re.IGNORECASE),
    re.compile(r"^[A-Z0-9_]*(?:API[_-]?KEY|SECRET|PASSWORD|TOKEN)[A-Z0-9_]*\s*=\s*[A-Za-z0-9_\-\.]{12,}\s*$", re.MULTILINE),
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"AIzaSy[a-zA-Z0-9_-]{33}", re.IGNORECASE),
]


def extract_python_symbols(code: str) -> list[dict[str, Any]]:
    """Extract class and function symbols from Python code using stdlib ast."""
    symbols: list[dict[str, Any]] = []
    try:
        tree = ast.parse(code)
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
    return sorted(symbols, key=lambda s: s["line"])


def classify_source_kind(rel_path: str) -> Literal["instruction", "code", "reported"]:
    """
    Epistemic taxonomy classifier.
    Never returns 'verified_observation' automatically.
    """
    norm = rel_path.lower().replace("\\", "/")
    parts = norm.split("/")
    filename = parts[-1]

    if "codelab" in filename or "readme" in filename:
        return "instruction"
    if filename.endswith(".py") or any(p in ("src", "tests", "lib") for p in parts[:-1]):
        return "code"
    return "reported"


def contains_secret(text: str) -> bool:
    """Check text against known credential and secret regex patterns."""
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            return True
    return False


def scan_sources(
    source_dir: Path,
    lab_id: str,
    out_dir: Path,
    chunk_size: int = 40,
    chunk_overlap: int = 5
) -> dict[str, Any]:
    """
    Scan source directory offline and produce traceable provenance artifacts.
    """
    source_dir = Path(source_dir).resolve()
    out_dir = Path(out_dir).resolve()

    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")
    if not source_dir.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {source_dir}")

    # Guard against overwriting source or invalid nesting
    if source_dir == out_dir:
        raise ValueError("out_dir cannot be identical to source_dir")

    out_dir.mkdir(parents=True, exist_ok=True)

    files_manifest: list[dict[str, Any]] = []
    skipped_manifest: list[dict[str, Any]] = []
    all_chunks: list[dict[str, Any]] = []

    # Gather candidate paths
    all_paths: list[Path] = []
    for root, dirs, files in os.walk(source_dir):
        root_path = Path(root)
        # Exclude hidden directories in-place to prune walk
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and d not in ("node_modules", "target", "dist", "build")
        ]
        for f in files:
            all_paths.append(root_path / f)

    # Sort deterministically
    all_paths.sort(key=lambda p: p.relative_to(source_dir).as_posix())

    for file_path in all_paths:
        try:
            rel_path = file_path.relative_to(source_dir).as_posix()
        except ValueError:
            continue

        # Check for path traversal or hidden/symlink
        parts = rel_path.split("/")
        if any(part.startswith(".") for part in parts) or any(part == ".." for part in parts):
            skipped_manifest.append({"path": rel_path, "reason": "hidden_or_traversal"})
            continue

        if file_path.is_symlink():
            skipped_manifest.append({"path": rel_path, "reason": "symlink_rejected"})
            continue

        ext = file_path.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            skipped_manifest.append({"path": rel_path, "reason": f"unsupported_extension_{ext}"})
            continue

        # Check exclusion patterns
        lower_name = file_path.name.lower()
        if lower_name.startswith(".env") or lower_name.startswith("tutor_turns") or lower_name.startswith("transcript"):
            skipped_manifest.append({"path": rel_path, "reason": "excluded_filename_pattern"})
            continue

        # Check size
        file_size = file_path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            skipped_manifest.append({"path": rel_path, "reason": "file_exceeds_size_limit"})
            continue

        # Read raw bytes & hash
        raw_bytes = file_path.read_bytes()
        file_sha256 = hashlib.sha256(raw_bytes).hexdigest()

        # Strict UTF-8 decode
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            skipped_manifest.append({"path": rel_path, "reason": "utf8_decode_error"})
            continue

        # Secret check
        if contains_secret(text):
            skipped_manifest.append({"path": rel_path, "reason": "credential_pattern_detected"})
            continue

        source_kind = classify_source_kind(rel_path)
        lines = text.splitlines(keepends=True)
        total_lines = len(lines)

        symbols = []
        if ext == ".py":
            symbols = extract_python_symbols(text)

        file_record: dict[str, Any] = {
            "path": rel_path,
            "sha256": file_sha256,
            "size_bytes": file_size,
            "total_lines": total_lines,
            "source_kind": source_kind,
            "symbols_count": len(symbols),
        }
        if symbols:
            file_record["symbols"] = symbols

        files_manifest.append(file_record)

        # Chunk lines
        if total_lines == 0:
            continue

        step = max(1, chunk_size - chunk_overlap)
        start_idx = 0

        while start_idx < total_lines:
            end_idx = min(start_idx + chunk_size, total_lines)
            chunk_slice = lines[start_idx:end_idx]
            chunk_text = "".join(chunk_slice)
            start_line = start_idx + 1
            end_line = end_idx

            chunk_sha256 = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
            chunk_id = f"{rel_path}:{start_line}-{end_line}"

            chunk_record = {
                "chunk_id": chunk_id,
                "lab_id": lab_id,
                "path": rel_path,
                "start_line": start_line,
                "end_line": end_line,
                "sha256": chunk_sha256,
                "file_sha256": file_sha256,
                "text": chunk_text,
                "source_kind": source_kind,
            }
            all_chunks.append(chunk_record)

            if end_idx >= total_lines:
                break
            start_idx += step

    # Deterministic manifest hash from canonical files JSON
    canonical_files_json = json.dumps(files_manifest, sort_keys=True, separators=(",", ":"))
    source_manifest_sha256 = hashlib.sha256(canonical_files_json.encode("utf-8")).hexdigest()

    manifest = {
        "lab_id": lab_id,
        "source_manifest_sha256": source_manifest_sha256,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files_count": len(files_manifest),
        "chunks_count": len(all_chunks),
        "files": files_manifest,
        "skipped": skipped_manifest,
    }

    # Write output artifacts
    manifest_path = out_dir / "source_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    chunks_path = out_dir / "source_chunks.jsonl"
    with open(chunks_path, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline source ingestion for Lab Simulator")
    parser.add_argument("--source-dir", type=Path, required=True, help="Input source directory")
    parser.add_argument("--lab-id", type=str, default="day03", help="Identifier of the lab (e.g. day03)")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output directory for artifacts")
    parser.add_argument("--chunk-size", type=int, default=40, help="Lines per chunk")
    parser.add_argument("--chunk-overlap", type=int, default=5, help="Lines overlapping between chunks")

    args = parser.parse_args()
    manifest = scan_sources(
        source_dir=args.source_dir,
        lab_id=args.lab_id,
        out_dir=args.out_dir,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    print(f"Successfully ingested {manifest['lab_id']}:")
    print(f"  Files indexed : {manifest['files_count']}")
    print(f"  Files skipped : {len(manifest['skipped'])}")
    print(f"  Chunks created: {manifest['chunks_count']}")
    print(f"  Manifest SHA256: {manifest['source_manifest_sha256']}")


if __name__ == "__main__":
    main()

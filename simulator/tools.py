"""
Lab Simulator — Codebase Intelligence Tools

Gives the simulation agent coding-agent capabilities: read files, search code,
analyze structure, and retrieve transcript evidence. The agent decides what to
read and when — no need to feed 100% of the codebase into context.

Follows Day04 tool convention: each tool is a plain function, registered in
TOOL_FUNCTIONS dict, with JSON Schema in TOOLS_SCHEMA list.
"""

import os
import re
import json
import hashlib
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Root of the lab data directory (immutable, never write here)
DATA_ROOT = Path(os.getenv(
    "LAB_DATA_ROOT",
    str(Path(__file__).resolve().parent.parent / "data"),
))

# Allowed lab directories the agent can explore
ALLOWED_LABS = {
    "day01": DATA_ROOT / "K4-Day01-Lab",
    "day02": DATA_ROOT / "K4-Day02-Lab",
    "day03": DATA_ROOT / "K4-Day03-Lab",
    "day04": DATA_ROOT / "K4-Day04-Lab",
}

TRANSCRIPT_DIR = DATA_ROOT / "vlearn-pack" / "transcript" if (DATA_ROOT / "vlearn-pack").exists() else None

# Safety: never read these patterns
BLOCKED_PATTERNS = re.compile(
    r"\.(env|pyc|pem|key|secret)$|__pycache__|\.git/|\.venv/|node_modules/",
    re.IGNORECASE,
)

MAX_FILE_BYTES = 32_000  # ~8K tokens at 4 chars/token
MAX_SEARCH_RESULTS = 20
MAX_LINES_CONTEXT = 5  # lines above/below a search hit


# ---------------------------------------------------------------------------
# Tool: list_files — directory inventory
# ---------------------------------------------------------------------------

def list_files(lab: str, path: str = "", max_depth: int = 3) -> dict[str, Any]:
    """List files and directories in a lab codebase, with sizes."""
    lab_root = ALLOWED_LABS.get(lab.lower().replace("day0", "day0").replace(" ", ""))
    if not lab_root:
        lab_root = ALLOWED_LABS.get(f"day0{lab}" if lab.isdigit() else lab)
    if not lab_root or not lab_root.exists():
        return {"status": "error", "message": f"Unknown lab: {lab}. Available: {list(ALLOWED_LABS.keys())}"}

    target = lab_root / path
    if not target.exists():
        return {"status": "error", "message": f"Path not found: {path}"}

    entries = []
    for item in sorted(target.rglob("*") if max_depth > 1 else target.iterdir()):
        rel = item.relative_to(lab_root)
        depth = len(rel.parts)
        if depth > max_depth:
            continue
        if BLOCKED_PATTERNS.search(str(rel)):
            continue
        entry = {"path": str(rel), "type": "dir" if item.is_dir() else "file"}
        if item.is_file():
            entry["size_bytes"] = item.stat().st_size
            entry["extension"] = item.suffix
        entries.append(entry)

    return {
        "status": "success",
        "lab": lab,
        "root": str(lab_root),
        "count": len(entries),
        "entries": entries[:50],  # cap output
    }


# ---------------------------------------------------------------------------
# Tool: read_file — read a specific file with optional line range
# ---------------------------------------------------------------------------

def read_file(lab: str, file_path: str, start_line: int = 1, end_line: int = 0) -> dict[str, Any]:
    """Read contents of a file in a lab codebase."""
    lab_root = ALLOWED_LABS.get(lab.lower().replace(" ", ""))
    if not lab_root:
        lab_root = ALLOWED_LABS.get(f"day0{lab}" if lab.isdigit() else lab)
    if not lab_root or not lab_root.exists():
        return {"status": "error", "message": f"Unknown lab: {lab}"}

    target = lab_root / file_path
    if not target.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}
    if not target.is_file():
        return {"status": "error", "message": f"Not a file: {file_path}"}
    if BLOCKED_PATTERNS.search(str(file_path)):
        return {"status": "blocked", "message": "Access to this file type is restricted"}
    if target.stat().st_size > MAX_FILE_BYTES * 2:
        return {"status": "error", "message": f"File too large ({target.stat().st_size} bytes). Use start_line/end_line."}

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"status": "error", "message": str(e)}

    lines = content.splitlines(keepends=True)
    total_lines = len(lines)

    if end_line <= 0:
        end_line = total_lines
    start_line = max(1, start_line)
    end_line = min(end_line, total_lines)

    selected = lines[start_line - 1 : end_line]
    text = "".join(selected)

    # Truncate if still too large
    if len(text) > MAX_FILE_BYTES:
        text = text[:MAX_FILE_BYTES] + f"\n... [TRUNCATED at {MAX_FILE_BYTES} chars, total {len(content)} chars]"

    return {
        "status": "success",
        "lab": lab,
        "file": file_path,
        "total_lines": total_lines,
        "showing": f"L{start_line}-L{end_line}",
        "content": text,
    }


# ---------------------------------------------------------------------------
# Tool: search_code — grep-like search across a lab codebase
# ---------------------------------------------------------------------------

def search_code(lab: str, query: str, file_pattern: str = "*.py") -> dict[str, Any]:
    """Search for a text pattern across files in a lab codebase."""
    lab_root = ALLOWED_LABS.get(lab.lower().replace(" ", ""))
    if not lab_root:
        lab_root = ALLOWED_LABS.get(f"day0{lab}" if lab.isdigit() else lab)
    if not lab_root or not lab_root.exists():
        return {"status": "error", "message": f"Unknown lab: {lab}"}

    results = []
    try:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
    except re.error:
        return {"status": "error", "message": f"Invalid search pattern: {query}"}

    for fpath in sorted(lab_root.rglob(file_pattern)):
        if BLOCKED_PATTERNS.search(str(fpath.relative_to(lab_root))):
            continue
        if not fpath.is_file() or fpath.stat().st_size > MAX_FILE_BYTES * 2:
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for i, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                results.append({
                    "file": str(fpath.relative_to(lab_root)),
                    "line": i,
                    "content": line.strip()[:200],
                })
                if len(results) >= MAX_SEARCH_RESULTS:
                    return {
                        "status": "success",
                        "lab": lab,
                        "query": query,
                        "match_count": len(results),
                        "truncated": True,
                        "results": results,
                    }

    return {
        "status": "success",
        "lab": lab,
        "query": query,
        "match_count": len(results),
        "truncated": False,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Tool: get_file_summary — AST-level summary of a Python file
# ---------------------------------------------------------------------------

def get_file_summary(lab: str, file_path: str) -> dict[str, Any]:
    """Get a structural summary of a Python file: functions, classes, imports."""
    read_result = read_file(lab, file_path)
    if read_result["status"] != "success":
        return read_result

    content = read_result["content"]
    summary: dict[str, Any] = {
        "status": "success",
        "lab": lab,
        "file": file_path,
        "total_lines": read_result["total_lines"],
    }

    # Extract imports
    imports = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            imports.append(stripped)
    summary["imports"] = imports

    # Extract function/class definitions with line numbers
    definitions = []
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("def ") or stripped.startswith("async def "):
            # Get signature (first line only)
            definitions.append({"line": i, "type": "function", "signature": stripped.rstrip(":")})
        elif stripped.startswith("class "):
            definitions.append({"line": i, "type": "class", "signature": stripped.rstrip(":")})
    summary["definitions"] = definitions

    # Extract docstring of the module (first triple-quote block)
    doc_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
    if doc_match:
        doc = doc_match.group(1).strip()
        summary["module_docstring"] = doc[:500]

    return summary


# ---------------------------------------------------------------------------
# Tool: search_transcript — search lecture transcripts by concept
# ---------------------------------------------------------------------------

def search_transcript(query: str, transcript_id: str = "") -> dict[str, Any]:
    """Search lecture transcripts for concepts. Returns [Txx-NNN] segment references."""
    if not TRANSCRIPT_DIR or not TRANSCRIPT_DIR.exists():
        return {"status": "error", "message": "Transcript directory not found"}

    results = []
    try:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
    except re.error:
        return {"status": "error", "message": f"Invalid query: {query}"}

    # Segment pattern: [Txx-NNN] markers
    segment_pattern = re.compile(r"\[T(\d{2})-(\d{3})\]")

    for fpath in sorted(TRANSCRIPT_DIR.glob("transcript-*-clean.md")):
        fname = fpath.name
        if transcript_id and transcript_id not in fname:
            continue

        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Split by segment markers
        segments = re.split(r"(\[T\d{2}-\d{3}\])", text)
        current_ref = ""
        for part in segments:
            seg_match = segment_pattern.match(part)
            if seg_match:
                current_ref = part
                continue
            if pattern.search(part) and current_ref:
                # Get first 300 chars of matching segment
                snippet = part.strip()[:300]
                results.append({
                    "transcript": fname,
                    "segment_ref": current_ref,
                    "snippet": snippet,
                })
                if len(results) >= MAX_SEARCH_RESULTS:
                    break

    return {
        "status": "success",
        "query": query,
        "match_count": len(results),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Tool: get_misconceptions — retrieve known misconceptions for a topic
# ---------------------------------------------------------------------------

# Hardcoded misconception bank for MVP (mined from discord-pack + chatlog)
_MISCONCEPTION_BANK = [
    {
        "id": "MC01", "lab": "day01", "concept": "temperature",
        "wrong": "Temperature cao = câu trả lời thông minh/tốt hơn",
        "correct": "Temperature kiểm soát randomness. Cao = diverse/creative, thấp = deterministic/focused. Không liên quan đến 'thông minh'.",
        "source": "discord:onboarding, chatlog:common_question",
    },
    {
        "id": "MC02", "lab": "day01", "concept": "model_selection",
        "wrong": "gpt-4o luôn tốt hơn gpt-4o-mini trong mọi trường hợp",
        "correct": "gpt-4o-mini rẻ hơn ~30x, nhanh hơn, và đủ tốt cho nhiều task đơn giản. Chọn model theo use case, không phải theo tên.",
        "source": "chatlog:model_comparison",
    },
    {
        "id": "MC03", "lab": "day01", "concept": "system_prompt",
        "wrong": "System prompt không ảnh hưởng nhiều đến kết quả",
        "correct": "System prompt kiểm soát persona, output format, safety boundaries, và citation behavior. Thiếu system prompt = hallucination cao.",
        "source": "transcript:T04-015",
    },
    {
        "id": "MC04", "lab": "day01", "concept": "tokenization",
        "wrong": "1 từ tiếng Việt = 1 token",
        "correct": "Tiếng Việt thường tốn 2-3 token/từ (do BPE tokenizer trained trên English). Budget token cần nhân 2-3x cho Vietnamese.",
        "source": "transcript:T04-042",
    },
    {
        "id": "MC05", "lab": "day01", "concept": "hallucination",
        "wrong": "Hallucination chỉ xảy ra khi model 'không biết'",
        "correct": "LLM có thể hallucinate ngay cả với thông tin nó 'biết'. Hallucination là artifact của next-token prediction, không phải thiếu knowledge.",
        "source": "transcript:T04-015, T05-010",
    },
    {
        "id": "MC06", "lab": "day01", "concept": "max_tokens",
        "wrong": "max_tokens càng cao thì câu trả lời càng tốt",
        "correct": "max_tokens chỉ giới hạn output length. Cao quá = tốn tiền + response dài không cần thiết. Set vừa đủ cho use case.",
        "source": "chatlog:api_params",
    },
    {
        "id": "MC07", "lab": "day01", "concept": "api_cost",
        "wrong": "Gọi API nhiều lần không tốn tiền đáng kể",
        "correct": "Mỗi lần gọi tính token input + output. 100 queries với gpt-4o có thể tốn $1-5. Budget management là kỹ năng production.",
        "source": "exercises:cost_calculation",
    },
]


def get_misconceptions(concept: str = "", lab: str = "day01") -> dict[str, Any]:
    """Get known misconceptions for a concept or lab."""
    results = []
    for mc in _MISCONCEPTION_BANK:
        if concept and concept.lower() not in mc["concept"].lower() and concept.lower() not in mc["wrong"].lower():
            continue
        if lab and mc["lab"] != lab.lower().replace(" ", ""):
            continue
        results.append(mc)
    return {
        "status": "success",
        "query": concept or "(all)",
        "lab": lab,
        "count": len(results),
        "misconceptions": results,
    }


# ---------------------------------------------------------------------------
# Registry — Day04 convention: TOOL_FUNCTIONS + TOOLS_SCHEMA
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS: dict[str, Any] = {
    "list_files": list_files,
    "read_file": read_file,
    "search_code": search_code,
    "get_file_summary": get_file_summary,
    "search_transcript": search_transcript,
    "get_misconceptions": get_misconceptions,
}

TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "list_files",
        "description": "List files and directories in a lab codebase. Use this first to understand project structure before reading specific files.",
        "parameters": {
            "type": "object",
            "properties": {
                "lab": {"type": "string", "description": "Lab identifier: 'day01', 'day02', 'day03', or 'day04'", "enum": ["day01", "day02", "day03", "day04"]},
                "path": {"type": "string", "description": "Relative path within the lab. Empty string for root.", "default": ""},
                "max_depth": {"type": "integer", "description": "Max directory depth to scan (1-5)", "default": 3},
            },
            "required": ["lab"],
        },
    },
    {
        "name": "read_file",
        "description": "Read contents of a specific file in a lab codebase. Use start_line/end_line for large files.",
        "parameters": {
            "type": "object",
            "properties": {
                "lab": {"type": "string", "enum": ["day01", "day02", "day03", "day04"]},
                "file_path": {"type": "string", "description": "Relative path to the file within the lab"},
                "start_line": {"type": "integer", "description": "First line to read (1-indexed)", "default": 1},
                "end_line": {"type": "integer", "description": "Last line to read (0 = end of file)", "default": 0},
            },
            "required": ["lab", "file_path"],
        },
    },
    {
        "name": "search_code",
        "description": "Search for a text pattern across files in a lab. Returns matching lines with file paths and line numbers.",
        "parameters": {
            "type": "object",
            "properties": {
                "lab": {"type": "string", "enum": ["day01", "day02", "day03", "day04"]},
                "query": {"type": "string", "description": "Text to search for (case-insensitive)"},
                "file_pattern": {"type": "string", "description": "Glob pattern for files to search", "default": "*.py"},
            },
            "required": ["lab", "query"],
        },
    },
    {
        "name": "get_file_summary",
        "description": "Get structural summary of a Python file: imports, function/class definitions with line numbers, module docstring. Use this before read_file to understand what's in a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "lab": {"type": "string", "enum": ["day01", "day02", "day03", "day04"]},
                "file_path": {"type": "string", "description": "Relative path to the .py file"},
            },
            "required": ["lab", "file_path"],
        },
    },
    {
        "name": "search_transcript",
        "description": "Search lecture transcripts for concepts. Returns [Txx-NNN] segment references that can be cited. Use to find authoritative explanations from course lectures.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Concept or keyword to search for in lecture transcripts"},
                "transcript_id": {"type": "string", "description": "Optional: filter to specific transcript (e.g. '04' for transcript-04)", "default": ""},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_misconceptions",
        "description": "Retrieve known student misconceptions about a concept. Use to proactively check if a student's reasoning matches common wrong beliefs.",
        "parameters": {
            "type": "object",
            "properties": {
                "concept": {"type": "string", "description": "Concept to check misconceptions for (e.g. 'temperature', 'hallucination')", "default": ""},
                "lab": {"type": "string", "description": "Filter by lab", "default": "day01"},
            },
            "required": [],
        },
    },
]

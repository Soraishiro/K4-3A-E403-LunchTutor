"""
Unified AI Agent & Tool Execution Layer for Lab Simulator.
Provides offline lexical retrieval, real OpenAI/Gemini tool calling,
and interactive CLI execution without external wrappers or mock data.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------------------
# Lexical Retrieval Engine
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
# Tool Registry & Schemas
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
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_sources",
                    "description": "Search code and documentation chunks by keywords or phrases.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query terms"},
                            "top_k": {"type": "integer", "default": 5, "description": "Number of results"},
                            "filter_kind": {"type": "string", "enum": ["instruction", "code", "reported"]}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_source_chunk",
                    "description": "Read the complete verified text and provenance of a specific chunk.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "chunk_id": {"type": "string", "description": "ID of chunk, e.g. 'docs/CODELAB.md:1-40'"}
                        },
                        "required": ["chunk_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_file_outline",
                    "description": "Get file outline with functions, classes, and line numbers extracted from AST.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative path of file, e.g. 'src/tools.py'"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_indexed_files",
                    "description": "List all files indexed in the lab with their line counts and categories.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filter_kind": {"type": "string", "enum": ["instruction", "code", "reported"]}
                        }
                    }
                }
            }
        ]


# ---------------------------------------------------------------------------
# LLM Provider Client
# ---------------------------------------------------------------------------
class LLMClient:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key.strip().strip('"').strip("'")
        self.model = model
        self.ssl_context = ssl._create_unverified_context()

    def chat_completion(self, messages: list[dict[str, Any]], tools: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        url = "https://api.openai.com/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
        )
        with urllib.request.urlopen(req, timeout=30, context=self.ssl_context) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]


# ---------------------------------------------------------------------------
# Agent Core & Socratic Prompts
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are the Lab Simulator AI Coach & Evidence Navigator.
Your mission is to guide learners through the lab codebase and codelab instructions using Socratic guidance.

STRICT OPERATING RULES:
1. NEVER hallucinate or invent code, line numbers, or instructions.
2. Every factual claim MUST be grounded in real chunks retrieved via your tools.
3. You have tools to:
   - list_indexed_files: see what files exist in the lab.
   - get_file_outline: see classes and functions in a file with exact line numbers.
   - search_sources: search keyword matches across all chunks.
   - read_source_chunk: read full text of a chunk.
4. When answering the learner:
   - Call tools to find the real evidence in the repo.
   - Provide clear, Socratic feedback with exact citations (file path and line ranges).
   - If there is a conflict or ambiguity in the lab materials (e.g. Task 2.1 in tools.py vs mcp_server.py), explicitly point out the conflict from the evidence.
"""


class LabSimAgent:
    def __init__(self, tool_registry: ToolRegistry, llm_client: LLMClient, trace_log_path: Optional[Path] = None):
        self.tools = tool_registry
        self.llm = llm_client
        self.trace_log_path = trace_log_path

    def run(self, user_query: str, max_iterations: int = 6) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_query}
        ]
        traces: list[dict[str, Any]] = []
        tools_schema = self.tools.get_tools_schema_openai()
        start_time = time.time()

        for iteration in range(max_iterations):
            step_start = time.time()
            assistant_msg = self.llm.chat_completion(messages, tools=tools_schema)
            messages.append(assistant_msg)

            tool_calls = assistant_msg.get("tool_calls", [])
            if not tool_calls:
                total_duration_ms = round((time.time() - start_time) * 1000, 2)
                result = {
                    "query": user_query,
                    "final_answer": assistant_msg.get("content", ""),
                    "iterations": iteration + 1,
                    "duration_ms": total_duration_ms,
                    "traces": traces,
                }
                self._log_trace(result)
                return result

            for tool_call in tool_calls:
                call_id = tool_call["id"]
                fn_name = tool_call["function"]["name"]
                fn_args_raw = tool_call["function"]["arguments"]
                try:
                    fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                except Exception:
                    fn_args = {}

                obs = self.tools.execute(fn_name, fn_args)
                traces.append({
                    "iteration": iteration + 1,
                    "tool": fn_name,
                    "arguments": fn_args,
                    "observation_summary": str(obs)[:200] + ("..." if len(str(obs)) > 200 else ""),
                    "step_latency_ms": round((time.time() - step_start) * 1000, 2)
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": fn_name,
                    "content": json.dumps(obs, ensure_ascii=False)
                })

        total_duration_ms = round((time.time() - start_time) * 1000, 2)
        result = {
            "query": user_query,
            "final_answer": "Reached maximum tool call iterations.",
            "iterations": max_iterations,
            "duration_ms": total_duration_ms,
            "traces": traces,
        }
        self._log_trace(result)
        return result

    def _log_trace(self, result: dict[str, Any]) -> None:
        if not self.trace_log_path:
            return
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **result
        }
        with open(self.trace_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# CLI Entrypoint (Zero extra script files)
# ---------------------------------------------------------------------------
def _find_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    env_path = Path("data/K4-Day03-Lab/.env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val and not val.startswith("your_"):
                    return val
    raise ValueError("OPENAI_API_KEY not found in environment or data/K4-Day03-Lab/.env")


def main() -> None:
    parser = argparse.ArgumentParser(description="LabSim AI Agent - Evidence-grounded Socratic Coach")
    parser.add_argument("--query", "-q", type=str, help="Learner question to ask the agent")
    parser.add_argument("--generated-dir", type=Path, default=Path("data/generated/day03"), help="Path to ingested artifacts")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="LLM model name")
    args = parser.parse_args()

    api_key = _find_api_key()
    registry = ToolRegistry(args.generated_dir)
    client = LLMClient(api_key=api_key, model=args.model)
    log_file = args.generated_dir / "agent_traces.jsonl"
    agent = LabSimAgent(registry, client, trace_log_path=log_file)

    if args.query:
        print(f"Learner Query: {args.query}\nThinking & inspecting codebase...")
        res = agent.run(args.query)
        print(f"\n--- Agent Response ({res['duration_ms']}ms, {res['iterations']} turns) ---")
        print(res["final_answer"])
    else:
        print("=== LabSim Interactive AI Agent (Type 'exit' to quit) ===")
        while True:
            try:
                q = input("\nLearner: ").strip()
                if not q or q.lower() in ("exit", "quit"):
                    break
                res = agent.run(q)
                print(f"\nCoach: {res['final_answer']}")
            except (KeyboardInterrupt, EOFError):
                break


if __name__ == "__main__":
    main()

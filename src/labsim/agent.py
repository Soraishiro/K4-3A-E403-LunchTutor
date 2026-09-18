"""
Standard AI Agent & Tool Execution Layer for Lab Simulator.
Connects real LLM to the ingested codebase index (source_manifest.json & source_chunks.jsonl).
Executes real tool calls to search, inspect outlines, and read chunks without hallucination.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from labsim.retrieval import (
    get_chunk_by_id,
    get_manifest_file_outline,
    list_manifest_files,
    load_chunk_index,
    search_sources,
)


# ---------------------------------------------------------------------------
# Tool Registry & Definitions
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
        """Search ingested code and document chunks by keyword/phrase."""
        raw_results = search_sources(self.chunks, self.lab_id, query, top_k=top_k, filter_kind=filter_kind)
        # Project concise evidence
        projected = []
        for r in raw_results:
            projected.append({
                "chunk_id": r.get("chunk_id"),
                "path": r.get("path"),
                "start_line": r.get("start_line"),
                "end_line": r.get("end_line"),
                "source_kind": r.get("source_kind"),
                "text_snippet": r.get("text", "")[:300] + ("..." if len(r.get("text", "")) > 300 else ""),
            })
        return projected

    def read_source_chunk(self, chunk_id: str) -> dict[str, Any]:
        """Read the exact text and hash of a chunk by chunk_id."""
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
        """Get the AST symbol structure (functions, classes) and line counts of an indexed file."""
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
        """List all indexed files and their classifications."""
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
        """Dispatch tool call."""
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
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    def get_tools_schema_openai(self) -> list[dict[str, Any]]:
        """Return OpenAI-compatible function calling schemas."""
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
                            "filter_kind": {
                                "type": "string",
                                "enum": ["instruction", "code", "reported"],
                                "description": "Filter by source kind"
                            }
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
        """Send chat completion request to OpenAI API."""
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
# LabSim Agent Core
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
   - Identify what they are asking.
   - Call tools to find the real evidence in the repo.
   - Provide clear, Socratic feedback with exact citations (file path and line ranges).
   - If there is a conflict or ambiguity in the lab materials (e.g. Task 2.1 in tools.py vs mcp_server.py), explicitly point out the conflict from the evidence.
"""


class LabSimAgent:
    def __init__(self, tool_registry: ToolRegistry, llm_client: LLMClient, trace_log_path: Optional[Path] = None):
        self.tools = tool_registry
        self.llm = llm_client
        self.trace_log_path = trace_log_path

    def run(self, user_query: str, max_iterations: int = 5) -> dict[str, Any]:
        """
        Execute ReAct loop:
        User Query -> LLM (calls tools) -> Execute Tools -> LLM -> Final Response.
        """
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
                # No more tools requested -> Final answer reached
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

            # Process all tool calls in this turn
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

                # Append tool observation back to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": fn_name,
                    "content": json.dumps(obs, ensure_ascii=False)
                })

        # Max iterations reached
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

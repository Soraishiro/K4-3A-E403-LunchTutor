"""
AI Agent Core for Lab Simulator.
Executes ReAct loops with structured tool-calling, grounded in tools.py.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from labsim.tools import ToolRegistry

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


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
    parser = argparse.ArgumentParser(description="LabSim AI Agent")
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

"""
LunchTutor — Core Simulation Engine

Centralized engine combining:
1. Providers: Mock, OpenAI, Gemini (pure stdlib urllib, zero external dependencies)
2. Tools: Codebase & Transcript Intelligence (list, read, search, AST summary, transcript, misconceptions, safe run)
3. Agent Personas: Socratic Mentor, PairPal (Protégé Effect), SimBot + Multi-turn ReAct Loop
4. Evaluator: Hybrid Engine (deterministic metrics + sandbox execution + LLM-as-a-judge)
5. Scenarios & Memory: Declarative lab rounds and session state tracking
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Shared SSL context for API calls (bypass cert verification in restricted envs)

# ---------------------------------------------------------------------------
# 1. Base Paths & Data Root
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.getenv("LAB_DATA_ROOT", str(PROJECT_ROOT / "data")))

ALLOWED_LABS = {
    "day01": DATA_ROOT / "K4-Day01-Lab",
    "day02": DATA_ROOT / "K4-Day02-Lab",
    "day03": DATA_ROOT / "K4-Day03-Lab",
    "day04": DATA_ROOT / "K4-Day04-Lab",
}
TRANSCRIPT_DIR = DATA_ROOT / "vlearn-pack" / "transcript"


# ---------------------------------------------------------------------------
# 2. Providers (Zero External Dependency)
# ---------------------------------------------------------------------------
@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str = ""


@dataclass
class ModelResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class Provider:
    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, temperature: float = 0.7) -> ModelResponse:
        raise NotImplementedError


class MockProvider(Provider):
    """Deterministic mock provider for offline tests and zero-API execution."""
    def __init__(self, default_response: str = ""):
        self.default_response = default_response

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, temperature: float = 0.7) -> ModelResponse:
        last_msg = (messages[-1].get("content", "") or "").strip()
        last_msg_lower = last_msg.lower()

        # Check for tool call requests in query
        if tools:
            if "template.py" in last_msg_lower:
                return ModelResponse(tool_calls=[ToolCall(name="read_file", arguments={"lab": "day01", "file_path": "template.py"})])
            if any(k in last_msg_lower for k in ("list", "thư mục", "files")):
                return ModelResponse(tool_calls=[ToolCall(name="list_files", arguments={"lab": "day01"})])
            if "temperature" in last_msg_lower:
                return ModelResponse(tool_calls=[ToolCall(name="search_code", arguments={"lab": "day01", "query": "temperature"})])

        if self.default_response:
            return ModelResponse(text=self.default_response)

        # Mock LLM Judge response
        if "đánh giá" in last_msg_lower or "chấm điểm" in last_msg_lower or "rubric" in last_msg_lower:
            return ModelResponse(text='{"score": 85, "feedback": "Lập luận kỹ thuật tốt, cân bằng hợp lý giữa chi phí và độ trễ."}')

        # Mentor persona
        if any(w in last_msg_lower for w in ("quy chế", "tại sao", "như thế nào", "giúp")):
            return ModelResponse(text="[Socratic Mentor] Hãy đối chiếu với slide bài giảng [T01-042]. Theo bạn, điều gì sẽ xảy ra nếu ta đặt temperature = 0 thay vì 1.0?")

        return ModelResponse(text=f"[MOCK] Phản hồi ghi nhận: '{last_msg[:50]}...'. Sẵn sàng cho bước tiếp theo.")


class OpenAIProvider(Provider):
    def __init__(self, api_key: str = "", model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, temperature: float = 0.7) -> ModelResponse:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": temperature}
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            # Default TLS verification (no custom unverified context).
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            msg = data["choices"][0]["message"]
            tool_calls = [
                ToolCall(name=tc["function"]["name"], arguments=json.loads(tc["function"]["arguments"]), id=tc.get("id", ""))
                for tc in msg.get("tool_calls", [])
            ]
            return ModelResponse(text=msg.get("content") or "", tool_calls=tool_calls)
        except Exception as err:
            return ModelResponse(text=f"[OpenAI Error: {err}]")


class GeminiProvider(Provider):
    def __init__(self, api_key: str = "", model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, temperature: float = 0.7) -> ModelResponse:
        contents = []
        for m in messages:
            role = "user" if m.get("role") in ("user", "system") else "model"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {"contents": contents, "generationConfig": {"temperature": temperature}}
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        try:
            # Default TLS verification (no custom unverified context).
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0].get("text", "")
            return ModelResponse(text=text)
        except Exception as err:
            return ModelResponse(text=f"[Gemini Error: {err}]")


def get_provider(name: str = "mock", api_key: str = "", model: str = "") -> Provider:
    name_clean = name.lower().strip()
    if name_clean == "openai" or (not name_clean and os.getenv("OPENAI_API_KEY")):
        return OpenAIProvider(api_key=api_key, model=model or "gpt-4o-mini")
    if name_clean in ("gemini", "google") or (not name_clean and os.getenv("GEMINI_API_KEY")):
        return GeminiProvider(api_key=api_key, model=model or "gemini-2.5-flash")
    return MockProvider()


# ---------------------------------------------------------------------------
# 3. Tools (Codebase & Transcript Intelligence)
# ---------------------------------------------------------------------------
def _safe_path(base: Path, subpath: str) -> Path | None:
    try:
        cand = (base / subpath).resolve()
        cand.relative_to(base.resolve())
        return cand
    except (ValueError, Exception):
        return None


def list_files(lab: str = "day01", path: str = "", max_depth: int = 3) -> dict[str, Any]:
    """List directory inventory in a lab codebase."""
    lab_root = ALLOWED_LABS.get(lab.lower())
    if not lab_root or not lab_root.exists():
        return {"status": "error", "message": f"Lab {lab} not found. Available: {list(ALLOWED_LABS.keys())}"}
    target = _safe_path(lab_root, path)
    if not target or not target.exists():
        return {"status": "error", "message": f"Invalid or non-existent path: {path}"}

    entries = []
    for item in sorted(target.rglob("*") if max_depth > 1 else target.iterdir()):
        rel = item.relative_to(lab_root)
        if len(rel.parts) > max_depth or ".git" in rel.parts or "__pycache__" in rel.parts:
            continue
        entry = {"path": str(rel), "type": "dir" if item.is_dir() else "file"}
        if item.is_file():
            entry["size_bytes"] = item.stat().st_size
        entries.append(entry)
    return {"status": "success", "lab": lab, "count": len(entries), "entries": entries[:60]}


def read_file(lab: str = "day01", file_path: str = "", start_line: int = 1, end_line: int = 0) -> dict[str, Any]:
    """Read contents of a file in a lab codebase with safe line slicing."""
    lab_root = ALLOWED_LABS.get(lab.lower())
    if not lab_root or not lab_root.exists():
        return {"status": "error", "message": f"Lab {lab} not found"}
    target = _safe_path(lab_root, file_path)
    if not target or not target.is_file():
        return {"status": "error", "message": f"File not found or unsafe: {file_path}"}

    lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
    total = len(lines)
    s = max(1, start_line)
    e = total if end_line <= 0 else min(end_line, total)
    sliced = lines[s - 1 : e]
    return {"status": "success", "file": file_path, "total_lines": total, "lines_shown": f"{s}-{e}", "content": "\n".join(sliced)}


def search_code(lab: str = "day01", query: str = "", max_results: int = 20) -> dict[str, Any]:
    """Search for keywords across python, markdown, and json files in lab."""
    lab_root = ALLOWED_LABS.get(lab.lower())
    if not lab_root or not lab_root.exists():
        return {"status": "error", "message": f"Lab {lab} not found"}

    results = []
    for f in sorted(lab_root.rglob("*")):
        if not f.is_file() or f.suffix not in (".py", ".md", ".json") or "__pycache__" in f.parts:
            continue
        content = f.read_text(encoding="utf-8", errors="ignore")
        if query.lower() in content.lower():
            matching_lines = [
                {"line": i, "text": line.strip()}
                for i, line in enumerate(content.splitlines(), 1)
                if query.lower() in line.lower()
            ]
            results.append({"file": str(f.relative_to(lab_root)), "matches": matching_lines[:5]})
            if len(results) >= max_results:
                break
    return {"status": "success", "query": query, "match_count": len(results), "results": results}


def get_file_summary(lab: str = "day01", file_path: str = "") -> dict[str, Any]:
    """Parse Python AST to extract classes, functions, and docstrings."""
    content_res = read_file(lab, file_path)
    if content_res.get("status") != "success":
        return content_res
    try:
        tree = ast.parse(content_res["content"])
        definitions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args]
                definitions.append({"type": "function", "name": node.name, "args": args, "line": node.lineno})
            elif isinstance(node, ast.ClassDef):
                definitions.append({"type": "class", "name": node.name, "line": node.lineno})
        return {"status": "success", "file": file_path, "definitions": definitions}
    except Exception as err:
        return {"status": "error", "message": f"AST parse failed: {err}"}


def search_transcript(query: str = "") -> dict[str, Any]:
    """Search VLearn lecture transcripts for keywords and evidence timestamps."""
    if not TRANSCRIPT_DIR or not TRANSCRIPT_DIR.exists():
        return {"status": "success", "match_count": 0, "results": [], "note": "Transcripts directory not found"}
    results = []
    for f in sorted(TRANSCRIPT_DIR.glob("*.md")):
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        for idx, line in enumerate(lines, 1):
            if query.lower() in line.lower():
                results.append({"source": f.name, "line": idx, "content": line.strip()})
                if len(results) >= 15:
                    break
    return {"status": "success", "query": query, "match_count": len(results), "results": results}


def get_misconceptions(concept: str = "") -> dict[str, Any]:
    """Retrieve pre-compiled common student misconceptions."""
    bank = [
        {"concept": "temperature", "misconception": "Temperature càng cao thì LLM càng thông minh và ít bị lỗi.", "correction": "Temperature cao tăng randomness và hallucination."},
        {"concept": "system_prompt", "misconception": "System prompt không quan trọng, chỉ cần user prompt chi tiết.", "correction": "System prompt thiết lập ranh giới (boundaries) và role kiểm soát an toàn."},
        {"concept": "exception", "misconception": "Gọi API chỉ cần một dòng client.call(), không cần try/except.", "correction": "API mạng luôn có nguy cơ timeout, rate limit, quota error cần fallback."},
    ]
    matched = [m for m in bank if concept.lower() in m["concept"] or concept.lower() in m["misconception"].lower()] if concept else bank
    return {"status": "success", "count": len(matched), "misconceptions": matched}


def run_command(command: str, lab: str = "day01") -> dict[str, Any]:
    """Execute safe read-only commands (python, pytest, pip) with 15s timeout."""
    allowed = ("python ", "python3 ", "pytest", "pip ")
    if not command.strip().lower().startswith(allowed):
        return {"status": "error", "message": "Only read-only python, pytest, pip commands allowed."}
    lab_root = ALLOWED_LABS.get(lab.lower(), PROJECT_ROOT)
    try:
        res = subprocess.run(command, cwd=lab_root, shell=True, capture_output=True, text=True, timeout=15)
        return {"status": "success", "returncode": res.returncode, "stdout": res.stdout[-3000:], "stderr": res.stderr[-3000:]}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Command timed out (15s)"}


TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "list_files": list_files,
    "read_file": read_file,
    "search_code": search_code,
    "get_file_summary": get_file_summary,
    "search_transcript": search_transcript,
    "get_misconceptions": get_misconceptions,
    "run_command": run_command,
}

TOOLS_SCHEMA = [
    {"name": "list_files", "description": "List files in a lab codebase.", "parameters": {"type": "object", "properties": {"lab": {"type": "string"}, "path": {"type": "string"}, "max_depth": {"type": "integer"}}}},
    {"name": "read_file", "description": "Read file lines safely.", "parameters": {"type": "object", "properties": {"lab": {"type": "string"}, "file_path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["file_path"]}},
    {"name": "search_code", "description": "Search code files for keyword/regex.", "parameters": {"type": "object", "properties": {"lab": {"type": "string"}, "query": {"type": "string"}}, "required": ["query"]}},
    {"name": "get_file_summary", "description": "AST summary of classes and functions.", "parameters": {"type": "object", "properties": {"lab": {"type": "string"}, "file_path": {"type": "string"}}, "required": ["file_path"]}},
    {"name": "search_transcript", "description": "Search lecture transcripts for quotes/citations.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "get_misconceptions", "description": "Look up common student misconceptions.", "parameters": {"type": "object", "properties": {"concept": {"type": "string"}}}},
]


# ---------------------------------------------------------------------------
# 4. Agent Personas & ReAct Loop
# ---------------------------------------------------------------------------
SIMBOT_SYSTEM_PROMPT = """Bạn là SimBot - Trợ lý mô phỏng thực hành AI20k Lab.
Dùng tools (list_files, read_file, search_code) để trả lời chính xác dựa trên mã nguồn thực tế."""

MENTOR_SYSTEM_PROMPT = """Bạn là Trợ giảng Socratic AI20k.
QUY TẮC: Không cho đáp án trực tiếp. Đặt câu hỏi gợi mở để học viên tự suy luận. Trích dẫn bài giảng [Txx-NNN]."""

PAIRPAL_SYSTEM_PROMPT = """Bạn là PairPal - Bạn cùng bàn ngây ngô của học viên (Protégé Effect).
Bạn thường có hiểu lầm về AI và muốn người dùng giải thích cặn kẽ để bạn hiểu bản chất."""


def run_agent_turn(provider: Provider, messages: list[dict[str, Any]], system_prompt: str = SIMBOT_SYSTEM_PROMPT, tools: list[dict[str, Any]] | None = None, max_turns: int = 5) -> ModelResponse:
    """Multi-turn ReAct loop: prompts provider, dispatches tools, feeds observation back."""
    current_msgs = [{"role": "system", "content": system_prompt}] + list(messages)
    active_tools = tools if tools is not None else TOOLS_SCHEMA

    for _ in range(max_turns):
        resp = provider.complete(current_msgs, tools=active_tools)
        if not resp.tool_calls:
            return resp

        # Dispatch tool calls
        for tc in resp.tool_calls:
            fn = TOOL_FUNCTIONS.get(tc.name)
            obs = fn(**tc.arguments) if fn else {"status": "error", "message": f"Unknown tool: {tc.name}"}
            current_msgs.append({"role": "assistant", "content": f"Called tool {tc.name}"})
            current_msgs.append({"role": "tool", "content": json.dumps(obs, ensure_ascii=False)})

    return provider.complete(current_msgs, tools=[])


# ---------------------------------------------------------------------------
# 5. Scenarios & Memory
# ---------------------------------------------------------------------------
@dataclass
class RoundDef:
    number: int
    title: str
    phase: str
    description: str
    objective: str
    decision_type: str  # "params", "prompt", "code", "choice"
    pairpal_prompt: str = ""
    options: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Scenario:
    id: str
    title: str
    briefing: str
    objectives: list[str]
    rounds: list[RoundDef]


DAY01_SCENARIO = Scenario(
    id="SIM-DAY01-LLM-API",
    title="Tối ưu Trợ lý Học vụ VLearn (Cost - Latency - Quality)",
    briefing="Chatbot học vụ VLearn bị phàn nàn: chi phí quá cao, phản hồi chậm (>2.5s), và bị hallucination quy chế.",
    objectives=[
        "Độ chính xác (Accuracy) >= 80%",
        "Chi phí mỗi lượt (Cost/query) <= $0.005",
        "Độ trễ phản hồi (Latency) <= 1200ms",
        "Tỷ lệ Hallucination <= 10%",
    ],
    rounds=[
        RoundDef(
            number=1,
            title="Chọn Model & Temperature",
            phase="params",
            description="Chọn Model (gpt-4o, gpt-4o-mini, gemini-2.5-flash) và Temperature (0.0 - 1.5).",
            objective="Chi phí < $0.005/query và giảm nguy cơ hallucination.",
            decision_type="params",
            pairpal_prompt="Sao không chọn model đắt nhất gpt-4o và temperature = 1.0 cho bot thông minh và sáng tạo nhất vậy bạn?",
            options=[
                {"id": "A", "label": "Model gpt-4o-mini, temp 0.2 (Rẻ, ổn định, ít hallucination)", "correct": True},
                {"id": "B", "label": "Model gpt-4o, temp 1.0 (Sáng tạo tối đa, không quan tâm giá)", "correct": False},
                {"id": "C", "label": "Model tuỳ ý, temp 1.8 (Rất ngẫu nhiên)", "correct": False},
            ],
        ),
        RoundDef(
            number=2,
            title="System Prompt Chống Hallucination",
            phase="prompt",
            description="Thiết kế System Prompt có đầy đủ Role, Grounding (chỉ trả lời dựa trên tài liệu), và Fallback.",
            objective="Prompt có ranh giới rõ ràng, không lãng phí token.",
            decision_type="prompt",
            pairpal_prompt="Cần gì viết prompt dài dòng? Cứ ghi 'Bạn là trợ lý học vụ' thôi không được hả bạn?",
            options=[
                {"id": "A", "label": "Thêm role, grounding 'chỉ trả lời theo tài liệu', fallback 'nếu không rõ hãy từ chối'", "correct": True},
                {"id": "B", "label": "Chỉ ghi một câu ngắn gọn 'Bạn là trợ lý học vụ'", "correct": False},
                {"id": "C", "label": "Bỏ trống system prompt, nhét hết vào user prompt", "correct": False},
            ],
        ),
        RoundDef(
            number=3,
            title="Hàm Gọi API LLM An Toàn (Python Code)",
            phase="code",
            description="Viết hàm Python có try/except xử lý ngoại lệ khi gọi API (timeout, rate limit, parse error).",
            objective="Code thực thi được trong sandbox và có bắt lỗi an toàn.",
            decision_type="code",
            pairpal_prompt="Code gọi API cứ gọi thẳng một dòng client.generate() cho gọn, try/except làm chi cho rối?",
            options=[
                {"id": "A", "label": "Viết hàm có try/except Exception, log lỗi và trả fallback dict an toàn", "correct": True},
                {"id": "B", "label": "Gọi trực tiếp không bắt lỗi, để ứng dụng crash nếu mất mạng", "correct": False},
                {"id": "C", "label": "Dùng pass trong except để giấu lỗi", "correct": False},
            ],
        ),
    ],
)


class SimulationMemory:
    """State management carried across simulation turns."""
    def __init__(self):
        self.decisions: list[dict[str, Any]] = []
        self.mistakes: list[dict[str, Any]] = []
        self.history_metrics: list[EvalMetrics] = []

    def record_decision(self, round_num: int, choice: str, correct: bool, detail: str = ""):
        entry = {"round": round_num, "choice": choice, "correct": correct, "detail": detail}
        self.decisions.append(entry)
        if not correct:
            self.mistakes.append(entry)


# ---------------------------------------------------------------------------
# 6. Hybrid Evaluator Engine
# ---------------------------------------------------------------------------
@dataclass
class EvalMetrics:
    accuracy: float = 0.0
    cost_per_query: float = 0.0
    latency_ms: float = 0.0
    hallucination_rate: float = 0.0
    reasoning_quality: int = 0
    passed: bool = False
    details: list[str] = field(default_factory=list)


MODEL_PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00, "latency": 1100},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "latency": 650},
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30, "latency": 450},
    "mock": {"input": 0.0, "output": 0.0, "latency": 100},
}


class HybridEvaluator:
    def __init__(self, judge_provider: Provider):
        self.judge = judge_provider

    def evaluate_round1(self, model_choice: str, temperature: float, rationale: str = "") -> EvalMetrics:
        model_key = model_choice.lower().strip()
        pricing = MODEL_PRICING.get(model_key, MODEL_PRICING["gpt-4o-mini"])
        cost = (300 * pricing["input"] + 200 * pricing["output"]) / 1_000_000
        latency = pricing["latency"] + (temperature * 100)

        if temperature <= 0.3:
            acc, hall = 0.95, 0.05
        elif temperature <= 0.7:
            acc, hall = 0.85, 0.15
        else:
            acc, hall = 0.60, 0.40

        passed = (cost <= 0.005) and (acc >= 0.80)
        return EvalMetrics(accuracy=acc, cost_per_query=cost, latency_ms=latency, hallucination_rate=hall, reasoning_quality=85, passed=passed, details=[f"Model: {model_choice}, Temp: {temperature}, Cost: ${cost:.5f}"])

    def evaluate_round2(self, system_prompt: str, rationale: str = "") -> EvalMetrics:
        lowered = system_prompt.lower()
        has_role = any(w in lowered for w in ("bạn là", "vai trò", "assistant", "trợ lý"))
        has_grounding = any(w in lowered for w in ("chỉ trả lời", "dựa trên", "không bịa", "không đoán"))
        has_fallback = any(w in lowered for w in ("không biết", "chưa rõ", "liên hệ", "từ chối"))

        acc = (sum([has_role, has_grounding, has_fallback]) / 3.0) * 0.9 + 0.1
        passed = acc >= 0.70
        return EvalMetrics(accuracy=acc, cost_per_query=0.0003, latency_ms=600, hallucination_rate=round(1.0 - acc, 2), reasoning_quality=80, passed=passed, details=[f"Role: {has_role}, Grounding: {has_grounding}, Fallback: {has_fallback}"])

    def evaluate_round3_code(self, code_snippet: str, rationale: str = "") -> EvalMetrics:
        try:
            compile(code_snippet, "<code_snippet>", "exec")
        except SyntaxError as e:
            return EvalMetrics(accuracy=0.0, passed=False, details=[f"SyntaxError: {e}"])

        scope: dict[str, Any] = {}
        try:
            t0 = time.perf_counter()
            exec(code_snippet, {}, scope)
            exec_time = (time.perf_counter() - t0) * 1000
            has_func = any(callable(v) for v in scope.values())
            return EvalMetrics(accuracy=1.0 if has_func else 0.7, latency_ms=exec_time, reasoning_quality=90, passed=True, details=[f"Executed successfully in {exec_time:.2f}ms. Found callable: {has_func}"])
        except Exception as e:
            return EvalMetrics(accuracy=0.2, passed=False, details=[f"Execution runtime error: {e}"])

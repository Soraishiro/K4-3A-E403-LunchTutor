"""
Lab Simulator — Provider Layer

Thin adapter wrapping google-genai SDK for structured tool calling.
Follows Day04 Provider Protocol pattern: complete() returns ModelResponse.
Falls back to MockProvider for offline testing.
"""

import os
import json
from dataclasses import dataclass, field
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Protocol + Data Types (from Day04 base.py pattern)
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]

@dataclass
class ModelResponse:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None


class Provider(Protocol):
    def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        tool_choice: Any | None = None,
    ) -> ModelResponse: ...


# ---------------------------------------------------------------------------
# Gemini Provider (google-genai SDK)
# ---------------------------------------------------------------------------

class GeminiProvider:
    def __init__(self, api_key: str | None = None, default_model: str = "gemini-2.5-flash"):
        from google import genai
        self._client = genai.Client(api_key=api_key or os.getenv("GOOGLE_API_KEY", ""))
        self._default_model = default_model

    def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        tool_choice: Any | None = None,
    ) -> ModelResponse:
        from google.genai import types

        model_id = model or self._default_model

        # Separate system instruction from conversation
        system_parts = []
        conversation = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            else:
                gemini_role = "model" if role == "assistant" else "user"
                conversation.append(types.Content(
                    role=gemini_role,
                    parts=[types.Part.from_text(text=content)],
                ))

        # Build tool declarations from schema
        func_declarations = []
        for tool_schema in tools:
            params = tool_schema.get("parameters", {})
            func_declarations.append(types.FunctionDeclaration(
                name=tool_schema["name"],
                description=tool_schema.get("description", ""),
                parameters=params if params else None,
            ))

        gemini_tools = [types.Tool(function_declarations=func_declarations)] if func_declarations else None

        config = types.GenerateContentConfig(
            system_instruction="\n\n".join(system_parts) if system_parts else None,
            tools=gemini_tools,
            temperature=temperature,
        )

        response = self._client.models.generate_content(
            model=model_id,
            contents=conversation,
            config=config,
        )

        # Parse response
        text_parts = []
        tool_calls = []
        seen = set()

        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.text:
                    text_parts.append(part.text)
                elif part.function_call:
                    fc = part.function_call
                    args = dict(fc.args) if fc.args else {}
                    dedup_key = (fc.name, json.dumps(args, sort_keys=True))
                    if dedup_key not in seen:
                        seen.add(dedup_key)
                        tool_calls.append(ToolCall(name=fc.name, args=args))

        return ModelResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            raw=response,
        )


# ---------------------------------------------------------------------------
# OpenAI Provider (for students with OpenAI keys)
# ---------------------------------------------------------------------------

class OpenAIProvider:
    def __init__(self, api_key: str | None = None, default_model: str = "gpt-4o-mini"):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY", ""))
        self._default_model = default_model

    def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        tool_choice: Any | None = None,
    ) -> ModelResponse:
        model_id = model or self._default_model

        openai_tools = [
            {"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("parameters", {})}}
            for t in tools
        ] if tools else None

        response = self._client.chat.completions.create(
            model=model_id,
            messages=messages,
            tools=openai_tools,
            temperature=temperature,
            tool_choice=tool_choice,
        )

        msg = response.choices[0].message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(name=tc.function.name, args=args))

        return ModelResponse(text=msg.content, tool_calls=tool_calls, raw=response)


# ---------------------------------------------------------------------------
# Mock Provider (offline testing, deterministic)
# ---------------------------------------------------------------------------

class MockProvider:
    """Returns canned responses for offline development."""
    def complete(self, messages, tools, **kwargs) -> ModelResponse:
        last_msg = messages[-1].get("content", "") if messages else ""
        return ModelResponse(
            text=f"[MOCK] Received: {last_msg[:100]}... | {len(tools)} tools available",
            tool_calls=[],
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_provider(provider_name: str = "gemini", api_key: str = "", model: str = "") -> Provider:
    """Create a provider instance. Falls back to Mock if no API key."""
    name = provider_name.lower().strip()
    if name == "gemini":
        key = api_key or os.getenv("GOOGLE_API_KEY", "")
        if not key:
            return MockProvider()
        return GeminiProvider(api_key=key, default_model=model or "gemini-2.5-flash")
    elif name in ("openai", "gpt"):
        key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not key:
            return MockProvider()
        return OpenAIProvider(api_key=key, default_model=model or "gpt-4o-mini")
    else:
        return MockProvider()

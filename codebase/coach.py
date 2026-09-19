"""
Bounded AI Coach for Lab Simulator.
Single call, viewed evidence only, hint levels, structured output validation.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from codebase.models import CoachFeedback, Evidence, HintLevel, SessionState, UncertaintyLevel
from codebase.tools import ToolRegistry


COACH_SYSTEM_PROMPT = """You are the Lab Simulator AI Coach.
Your role: guide the learner through Socratic questioning based ONLY on evidence they have viewed.

STRICT RULES:
1. NEVER provide answers, solutions, or code directly.
2. ONLY use evidence explicitly provided in the context (viewed_evidence).
3. If evidence is insufficient, ask what they want to investigate next.
4. Output MUST be valid JSON matching the CoachFeedback schema.
5. Distinguish: observation (what evidence shows) vs inference (learner's claim).
6. Cite evidence_ids from viewed_evidence only.
7. Set uncertainty: LOW if evidence directly addresses hypothesis, MEDIUM if partial, HIGH if gap remains.

Hint levels:
- 0 (QUESTION): Ask a clarifying question based on evidence.
- 1 (REASONING_GAP): Point out what's missing in their reasoning.
- 2 (DIAGNOSTIC_CHECK): Suggest a specific check or evidence to look at.

JSON SCHEMA:
{
  "observation_acknowledged": "string - what the viewed evidence shows",
  "unsupported_inference": "string - what learner claims but evidence doesn't support",
  "next_question": "string - Socratic question to guide deeper",
  "cited_evidence_ids": ["string"] - subset of viewed evidence IDs",
  "uncertainty": "LOW | MEDIUM | HIGH"
}"""


class CoachClient:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key.strip().strip('"').strip("'")
        self.model = model

    def generate(self, messages: list[dict[str, Any]]) -> str:
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
        )
        # Default TLS verification (no custom unverified context).
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def build_coach_context(
    session: SessionState,
    bundle_evidence: list[Evidence],
    objective: str,
    hint_level: HintLevel
) -> list[dict[str, Any]]:
    """Build context with ONLY viewed evidence."""
    viewed = [e for e in bundle_evidence if e.evidence_id in session.viewed_evidence_ids]

    evidence_block = ""
    if viewed:
        evidence_block = "\n\nVIEWED EVIDENCE:\n"
        for e in viewed:
            evidence_block += f"\n--- {e.evidence_id} ({e.source_kind.value}) ---\n"
            evidence_block += f"Source: {e.source.path}:{e.source.start_line}-{e.source.end_line}\n"
            evidence_block += f"{e.excerpt}\n"
    else:
        evidence_block = "\n\nVIEWED EVIDENCE: (none - learner hasn't opened any evidence yet)"

    hypothesis = session.hypothesis_versions[-1] if session.hypothesis_versions else "(no hypothesis yet)"

    hint_instruction = {
        HintLevel.QUESTION: "Ask a clarifying question to help them identify what evidence they need.",
        HintLevel.REASONING_GAP: "Point out the specific gap between their hypothesis and the viewed evidence.",
        HintLevel.DIAGNOSTIC_CHECK: "Suggest a specific evidence card they should open or a check they should perform.",
    }[hint_level]

    user_prompt = f"""LAB OBJECTIVE: {objective}

LEARNER'S HYPOTHESIS: {hypothesis}{evidence_block}

HINT LEVEL: {hint_level.name} ({hint_level.value})
INSTRUCTION: {hint_instruction}

Provide feedback as JSON per schema."""

    return [
        {"role": "system", "content": COACH_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def validate_coach_output(raw: str, viewed_evidence_ids: list[str]) -> CoachFeedback:
    """Parse and validate coach output."""
    data = json.loads(raw)

    # Validate cited evidence IDs are subset of viewed
    cited = data.get("cited_evidence_ids", [])
    for cid in cited:
        if cid not in viewed_evidence_ids:
            raise ValueError(f"Coach cited unviewed evidence: {cid}")

    # Ensure required fields
    required = ["observation_acknowledged", "unsupported_inference", "next_question", "cited_evidence_ids", "uncertainty"]
    for field in required:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    # Validate uncertainty enum
    if data["uncertainty"] not in [u.value for u in UncertaintyLevel]:
        raise ValueError(f"Invalid uncertainty: {data['uncertainty']}")

    return CoachFeedback(**data)


def get_coach_feedback(
    session: SessionState,
    bundle_evidence: list[Evidence],
    objective: str,
    hint_level: HintLevel,
    client: CoachClient
) -> CoachFeedback:
    """Single bounded coach call with validation."""
    messages = build_coach_context(session, bundle_evidence, objective, hint_level)
    raw = client.generate(messages)
    viewed_ids = session.viewed_evidence_ids
    return validate_coach_output(raw, viewed_ids)
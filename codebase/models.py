"""
Pydantic models for Lab Simulator MVP.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class SourceKind(str, Enum):
    INSTRUCTION = "instruction"
    CODE = "code"
    REPORTED = "reported"
    VERIFIED_OBSERVATION = "verified_observation"
    HYPOTHETICAL = "hypothetical"


class QuestionKind(str, Enum):
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"


class HintLevel(int, Enum):
    QUESTION = 0
    REASONING_GAP = 1
    DIAGNOSTIC_CHECK = 2


class UncertaintyLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SourceRef(BaseModel):
    path: str
    start_line: int
    end_line: int
    sha256: str


class Evidence(BaseModel):
    evidence_id: str
    title: str
    excerpt: str
    source: SourceRef
    source_kind: SourceKind


class CoachFeedback(BaseModel):
    observation_acknowledged: str
    unsupported_inference: str
    next_question: str
    cited_evidence_ids: list[str]
    uncertainty: UncertaintyLevel


class Question(BaseModel):
    question_id: str
    kind: QuestionKind
    prompt: str
    options: dict[str, str]
    answer_key: list[str]
    explanation: str


class QuizAttempt(BaseModel):
    question_id: str
    selected: list[str]
    correct: bool
    attempt_number: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    post_reveal: bool = False


class SessionState(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    lab_id: str | None = None
    current_checkpoint: str | None = None
    checkpoint_completed: dict[str, bool] = Field(default_factory=dict)
    viewed_evidence_ids: list[str] = Field(default_factory=list)
    hypothesis_versions: list[str] = Field(default_factory=list)
    hint_level: HintLevel = HintLevel.QUESTION
    viewed_tip_ids: list[str] = Field(default_factory=list)
    quiz_attempts: list[QuizAttempt] = Field(default_factory=list)
    self_report: Optional[str] = None
    self_report_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# In-memory session store
_sessions: dict[str, SessionState] = {}


def create_session() -> SessionState:
    session = SessionState()
    _sessions[session.session_id] = session
    return session


def get_session(session_id: str) -> Optional[SessionState]:
    return _sessions.get(session_id)


def update_session(session_id: str, **kwargs) -> Optional[SessionState]:
    session = _sessions.get(session_id)
    if session:
        for k, v in kwargs.items():
            setattr(session, k, v)
    return session
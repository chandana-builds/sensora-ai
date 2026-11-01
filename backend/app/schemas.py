"""Pydantic request/response models."""
from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ExperienceLevel = Literal["beginner", "experienced"]
SessionStatus = Literal["active", "resolved", "unresolved", "escalated", "abandoned"]
CompletionStatus = Literal["resolved", "unresolved", "escalated", "abandoned"]
MessageRole = Literal["user", "assistant", "system"]
InputMode = Literal["text", "speech"]
SafetyLevelName = Literal["ok", "caution", "stop"]
StepStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]
StepVerification = Literal["not_verified", "user_confirmed", "visually_verified"]
ClientStepVerification = Literal["not_verified", "user_confirmed"]  # clients may not claim visual verification

Text = Annotated[str, StringConstraints(strip_whitespace=True)]

DEFAULT_PREFERENCES: dict = {
    "experience_level": "beginner",
    "speak_responses": True,
    "speech_rate": 1.0,
    "larger_text": False,
    "high_contrast": False,
    "reduce_motion": False,
    "save_transcripts": True,
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── Safety ────────────────────────────────────────────────────────────────
class SafetyAssessmentOut(BaseModel):
    level: SafetyLevelName
    categories: list[str]
    guidance: list[str]


class SafetyCheckIn(_Strict):
    text: Text = Field(min_length=1, max_length=8000)


# ── Preferences ───────────────────────────────────────────────────────────
class PreferencesOut(BaseModel):
    experience_level: ExperienceLevel
    speak_responses: bool
    speech_rate: float
    larger_text: bool
    high_contrast: bool
    reduce_motion: bool
    save_transcripts: bool
    updated_at: Optional[datetime] = None


class PreferencesUpdate(_Strict):
    experience_level: Optional[ExperienceLevel] = None
    speak_responses: Optional[bool] = None
    speech_rate: Optional[float] = Field(None, ge=0.5, le=2.0)
    larger_text: Optional[bool] = None
    high_contrast: Optional[bool] = None
    reduce_motion: Optional[bool] = None
    save_transcripts: Optional[bool] = None


# ── Sessions ──────────────────────────────────────────────────────────────
class SessionCreate(_Strict):
    device_name: Optional[Text] = Field(None, max_length=120)
    problem_description: Optional[Text] = Field(None, max_length=4000)
    experience_level: Optional[ExperienceLevel] = None

    @field_validator("device_name", "problem_description")
    @classmethod
    def _blank_to_none(cls, v):
        return v or None


class SessionUpdate(_Strict):
    device_name: Optional[Text] = Field(None, max_length=120)
    problem_description: Optional[Text] = Field(None, max_length=4000)
    experience_level: Optional[ExperienceLevel] = None


class SessionComplete(_Strict):
    status: CompletionStatus
    summary: Optional[Text] = Field(None, max_length=2000)
    unresolved_issues: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]] = Field(
        default_factory=list, max_length=20
    )


class SessionOut(BaseModel):
    id: str
    title: str
    device_name: Optional[str] = None
    problem_description: Optional[str] = None
    experience_level: ExperienceLevel
    status: SessionStatus
    started_at: datetime
    ended_at: Optional[datetime] = None
    updated_at: datetime


class SessionPage(BaseModel):
    items: list[SessionOut]
    has_more: bool
    limit: int
    offset: int


# ── Messages ──────────────────────────────────────────────────────────────
class MessageCreate(_Strict):
    # Clients can only create *user* messages. Assistant/system messages are
    # created by server-side orchestration, so the API can never be used to fake AI replies.
    content: Text = Field(min_length=1, max_length=4000)
    input_mode: InputMode = "text"


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: MessageRole
    content: str
    input_mode: InputMode
    safety_level: SafetyLevelName
    created_at: datetime


class MessageCreated(BaseModel):
    message: MessageOut
    safety: SafetyAssessmentOut


# ── Steps ─────────────────────────────────────────────────────────────────
class StepCreate(_Strict):
    instruction: Text = Field(min_length=1, max_length=1000)


class StepUpdate(_Strict):
    status: Optional[StepStatus] = None
    outcome_note: Optional[Text] = Field(None, max_length=1000)
    verification: Optional[ClientStepVerification] = None


class StepOut(BaseModel):
    id: str
    session_id: str
    step_number: int
    instruction: str
    status: StepStatus
    verification: StepVerification
    outcome_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ── Summary & detail ──────────────────────────────────────────────────────
class SummaryOut(BaseModel):
    session_id: str
    summary: str
    unresolved_issues: list[str]
    generated_by: Literal["user", "system", "ai"]
    created_at: datetime
    updated_at: datetime


class SessionDetail(SessionOut):
    messages: list[MessageOut]
    steps: list[StepOut]
    summary: Optional[SummaryOut] = None


class SessionCreated(SessionOut):
    safety: SafetyAssessmentOut


# ── Health ────────────────────────────────────────────────────────────────
class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    time: datetime
    database: dict
    ai: dict
    auth: dict

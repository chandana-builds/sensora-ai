"""Structured troubleshooting response + turn API schemas (Pydantic v2)."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SafetyStatus(str, Enum):
    ok = "ok"
    caution = "caution"
    stop = "stop"


class Confidence(BaseModel):
    level: Literal["low", "medium", "high"] = "low"
    note: str = Field(default="", max_length=300)


class LikelyCause(BaseModel):
    cause: str = Field(max_length=200)
    likelihood: Literal["low", "medium", "high"] = "low"


class CurrentStep(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=1, max_length=400)
    expected_result: str = Field(default="", max_length=250)


class TroubleshootingResponse(BaseModel):
    assistant_message: str = Field(min_length=1, max_length=900)
    observations: list[str] = Field(default_factory=list, max_length=12)
    likely_causes: list[LikelyCause] = Field(default_factory=list, max_length=4)
    confidence: Confidence = Field(default_factory=Confidence)
    current_step: CurrentStep | None = None
    requested_user_action: str | None = Field(default=None, max_length=300)
    requires_new_image: bool = False
    verification_required: bool = False
    safety_status: SafetyStatus = SafetyStatus.ok
    escalation_recommended: bool = False

    @model_validator(mode="after")
    def _one_step_and_safe(self) -> "TroubleshootingResponse":
        if self.safety_status == SafetyStatus.stop or self.escalation_recommended:
            self.current_step = None
            self.requested_user_action = None
            self.verification_required = False
        elif self.current_step and not self.requested_user_action:
            self.requested_user_action = self.current_step.instruction
        return self


class TurnRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    input_mode: Literal["voice", "text"] = "text"
    frames: list[str] = Field(default_factory=list, max_length=3, description="base64 JPEG, no data: prefix")
    user_level: Literal["beginner", "experienced"] | None = None


class TranscribeResponse(BaseModel):
    text: str
    provider: str
    simulated: bool


class AIStatus(BaseModel):
    mode: Literal["real", "demo"]
    simulated: bool
    transcription: str
    vision: str
    reasoning: str
    note: str
    providers: list[str] = Field(default_factory=list)
    provider_status: dict[str, Any] = Field(default_factory=dict)

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .schemas_ai import TurnRequest


class AgentTurnRequest(TurnRequest):
    reported_step_done: bool = False   # explicit "I've done this step" button; never treated as verification


class CompleteRequest(BaseModel):
    status: Literal["resolved", "unresolved", "abandoned"] | None = None


class ConsentRequest(BaseModel):
    evidence_consent: bool


class ExportRequest(BaseModel):
    pathway: Literal["remote_expert", "local_technician"] = "local_technician"
    include_evidence: bool = False
    consent_to_share: bool = False
    format: Literal["md", "html"] = "md"


class LevelRequest(BaseModel):
    level: Literal["beginner", "experienced"] | None = None
    remember: bool = False             # True = the user consents to saving it for future sessions

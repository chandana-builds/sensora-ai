"""Provider interfaces. Speech and vision/reasoning are separate capabilities."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence


class ProviderError(Exception):
    """A model/API call failed. Never swallowed into a fake answer."""

    def __init__(self, message: str, *, code: str = "provider_error",
                 status: int | None = None, retryable: bool = False,
                 retry_after: float | None = None) -> None:
        super().__init__(message)
        self.message, self.code, self.status = message, code, status
        self.retryable, self.retry_after = retryable, retry_after


class ProviderNotConfigured(ProviderError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="not_configured", status=503)


@dataclass
class TranscriptionResult:
    text: str
    provider: str
    simulated: bool = False


@dataclass
class VisionResult:
    observations: list[str]
    provider: str
    device_guess: str | None = None
    visible_text: list[str] = field(default_factory=list)  # model numbers, error codes
    image_quality: str = "good"  # good | poor | unusable
    needs_closer_view: bool = False
    simulated: bool = False


class Transcriber(Protocol):
    async def transcribe(self, wav: bytes, *, language_bias: Sequence[str] | None = None) -> TranscriptionResult: ...


class VisionAnalyzer(Protocol):
    async def analyze(self, frames: Sequence[bytes], *, context: str) -> VisionResult: ...


class Reasoner(Protocol):
    async def reason(self, *, system: str, history: list[dict[str, str]], user_text: str,
                     vision: VisionResult | None, context: dict[str, Any]) -> dict[str, Any]:
        """Return the raw JSON dict; the orchestrator validates it with Pydantic."""
        ...

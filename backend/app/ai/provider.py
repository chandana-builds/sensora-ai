"""AI provider abstraction (interfaces only in Milestone 1).

Speech transcription, visual understanding and reasoning are SEPARATE
capabilities so each can be swapped independently. No implementation ships in
Milestone 1, and nothing here returns canned or mock model output. Until a
real provider is configured, `get_ai_status()` reports `not_configured`.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AIStatus:
    status: str  # "not_configured" | "ready" | "error"
    detail: str

    def to_dict(self) -> dict:
        return {"status": self.status, "detail": self.detail}


class TranscriptionProvider(ABC):
    @abstractmethod
    def transcribe(self, audio: bytes, mime_type: str) -> str: ...


class VisionProvider(ABC):
    @abstractmethod
    def describe_frame(self, image: bytes, mime_type: str, question: str) -> str: ...


class ReasoningProvider(ABC):
    @abstractmethod
    def next_instruction(self, context: dict) -> str: ...


def get_ai_status() -> AIStatus:
    try:
        from .config import load_ai_settings
        s = load_ai_settings()
        if s.effective_mode == "demo":
            return AIStatus(
                "ready",
                f"Demo mode active (scenario: {s.demo_scenario}, responses simulated)",
            )
        if s.api_key:
            return AIStatus(
                "ready",
                f"Meta AI connected (reasoning={s.reasoning_model}, vision={s.vision_model}, stt={s.stt_model})",
            )
        return AIStatus(
            "not_configured",
            "MODEL_API_KEY missing.",
        )
    except Exception:
        return AIStatus(
            "not_configured",
            "No AI provider is connected in this build. Sensora will not generate replies yet.",
        )

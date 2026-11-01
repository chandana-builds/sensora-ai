from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .base import ProviderNotConfigured, Reasoner, Transcriber, VisionAnalyzer
from .config import AISettings
from .demo_provider import DemoReasoner, DemoTranscriber, DemoVision
from .demo_provider_v3 import DemoReasonerV3
from .router import (
    CircuitBreaker,
    MultiProviderReasoner,
    MultiProviderTranscriber,
    MultiProviderVision,
    SafeDeterministicFallbackReasoner,
)

log = logging.getLogger("sensora.ai.factory")


@dataclass
class Providers:
    transcriber: Transcriber
    vision: VisionAnalyzer
    reasoner: Reasoner
    mode: str  # "real" | "demo"
    circuit_breaker: CircuitBreaker | None = None
    configured_providers: list[str] = None

    @property
    def simulated(self) -> bool:
        return self.mode == "demo"


def build_providers(s: AISettings, client: Any = None) -> Providers:
    mode = s.effective_mode
    if mode == "demo":
        return Providers(
            DemoTranscriber(),
            DemoVision(s.demo_scenario),
            DemoReasonerV3(s.demo_scenario),
            "demo",
            configured_providers=["demo"],
        )

    # Multi-provider setup
    transcribers: list[tuple[str, Transcriber]] = []
    vision_providers: list[tuple[str, VisionAnalyzer]] = []
    reasoners: list[tuple[str, Reasoner]] = []
    configured_list: list[str] = []

    for name in s.provider_order:
        if name == "meta" and s.api_key:
            from .meta_provider import MetaReasoner, MetaTranscriber, MetaVision
            transcribers.append(("meta", MetaTranscriber(s, client=client)))
            vision_providers.append(("meta", MetaVision(s, client=client)))
            reasoners.append(("meta", MetaReasoner(s, client=client)))
            configured_list.append("meta")

        elif name == "gemini" and s.gemini_api_key:
            from .gemini_provider import GeminiReasoner, GeminiVision
            # Gemini provides vision + reasoning
            vision_providers.append(("gemini", GeminiVision(s, client=client)))
            reasoners.append(("gemini", GeminiReasoner(s, client=client)))
            configured_list.append("gemini")

        elif name == "groq" and s.groq_api_key:
            from .groq_provider import GroqReasoner, GroqTranscriber, GroqVision
            # Groq provides STT (whisper) + vision (llama-3.2 vision) + reasoning
            transcribers.append(("groq", GroqTranscriber(s, client=client)))
            vision_providers.append(("groq", GroqVision(s, client=client)))
            reasoners.append(("groq", GroqReasoner(s, client=client)))
            configured_list.append("groq")

    if not reasoners:
        raise ProviderNotConfigured(
            "AI_MODE=real but no active provider keys found. "
            "Please configure MODEL_API_KEY, GEMINI_API_KEY, or GROQ_API_KEY."
        )

    # Fallback transcriber if none configured
    if not transcribers:
        transcribers.append(("demo", DemoTranscriber()))

    cb = CircuitBreaker(default_cooldown_s=s.cooldown_s)
    multi_transcriber = MultiProviderTranscriber(transcribers, cb, max_retries=s.max_retries)
    multi_vision = MultiProviderVision(vision_providers, cb, max_retries=s.max_retries)
    fallback_reasoner = SafeDeterministicFallbackReasoner()
    multi_reasoner = MultiProviderReasoner(reasoners, cb, fallback_reasoner, max_retries=s.max_retries)

    return Providers(
        transcriber=multi_transcriber,
        vision=multi_vision,
        reasoner=multi_reasoner,
        mode="real",
        circuit_breaker=cb,
        configured_providers=configured_list,
    )

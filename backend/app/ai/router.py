"""Central Multi-Provider Router, Circuit Breaker, and Capability-Specific Fallback Orchestrator.

Provides transparent, ordered fallback between Meta, Google Gemini, Groq, and safe deterministic
fallbacks while strictly enforcing health cooldowns, capability checks, and safety.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Sequence

from .base import (
    ProviderError,
    ProviderNotConfigured,
    Reasoner,
    Transcriber,
    TranscriptionResult,
    VisionAnalyzer,
    VisionResult,
)
from .config import AISettings

log = logging.getLogger("sensora.ai.router")


@dataclass
class ProviderHealth:
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    cooldown_until: float = 0.0
    last_error: str | None = None
    is_permanently_disabled: bool = False  # e.g. invalid credentials


class CircuitBreaker:
    """Tracks provider availability, rate-limiting, and cooldown windows."""

    def __init__(self, default_cooldown_s: float = 60.0, max_consecutive_failures: int = 2) -> None:
        self.default_cooldown_s = default_cooldown_s
        self.max_consecutive_failures = max_consecutive_failures
        self._health: dict[str, ProviderHealth] = {}

    def get_health(self, provider_id: str) -> ProviderHealth:
        if provider_id not in self._health:
            self._health[provider_id] = ProviderHealth()
        return self._health[provider_id]

    @property
    def auth_disabled(self) -> set[str]:
        return {pid for pid, h in self._health.items() if h.is_permanently_disabled}

    def is_cooling_down(self, provider_id: str) -> bool:
        h = self.get_health(provider_id)
        return not h.is_permanently_disabled and time.time() < h.cooldown_until

    def is_available(self, provider_id: str) -> bool:
        h = self.get_health(provider_id)
        if h.is_permanently_disabled:
            return False
        if time.time() < h.cooldown_until:
            return False
        return True

    def record_success(self, provider_id: str) -> None:
        h = self.get_health(provider_id)
        h.consecutive_failures = 0
        h.last_error = None
        h.cooldown_until = 0.0

    def record_failure(self, provider_id: str, error: Exception | None = None) -> float:
        h = self.get_health(provider_id)
        h.consecutive_failures += 1
        h.last_failure_time = time.time()
        h.last_error = str(error) if error else "failure"

        cooldown = self.default_cooldown_s

        if isinstance(error, ProviderError):
            # Auth or permissions failure -> long cooldown or permanent disable
            if error.code == "auth_failed" or error.status in (401, 403):
                h.is_permanently_disabled = True
                log.error("Provider %s disabled due to invalid credentials or permissions.", provider_id)
                return 86400.0

            # Endpoint or model unavailable -> extended cooldown
            if error.code == "model_unavailable" or error.status == 404:
                cooldown = max(self.default_cooldown_s * 5, 300.0)

            # Rate limited with explicit Retry-After
            if error.code == "rate_limited" and error.retry_after:
                cooldown = max(error.retry_after, self.default_cooldown_s)

        # Trip cooldown if consecutive failures reach threshold or specific error occurred
        if h.consecutive_failures >= self.max_consecutive_failures or (isinstance(error, ProviderError) and error.status in (404, 429)):
            h.cooldown_until = time.time() + cooldown
            log.warning("Provider %s in cooldown for %.1fs after error: %s", provider_id, cooldown, error)
            return cooldown

        return 0.0


class SafeDeterministicFallbackReasoner:
    """Safe, transparent fallback when all external AI providers fail."""
    name = "deterministic_fallback"

    async def reason(
        self,
        *,
        system: str,
        history: list[dict[str, str]],
        user_text: str,
        vision: VisionResult | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "assistant_message": (
                "Sensora AI is currently operating in safe offline mode because our AI service providers are temporarily unavailable. "
                "For your safety, automated physical repair instructions are suspended right now. "
                "Please do not attempt to open appliances or touch exposed wiring. "
                "You can retry your question in a moment, or choose to escalate this issue to a certified technician."
            ),
            "observations": ["Automated diagnosis offline"],
            "likely_causes": [
                {"cause": "AI provider service outage or network disruption", "likelihood": "high"}
            ],
            "confidence": {"level": "low", "note": "Deterministic safety fallback engaged"},
            "current_step": None,
            "requested_user_action": "Please wait a moment and retry, or contact a certified technician.",
            "requires_new_image": False,
            "verification_required": False,
            "safety_status": "caution",
            "escalation_recommended": True,
            "_provider": "deterministic_fallback",
        }


async def retry_with_backoff(
    fn: Callable[[], Coroutine[Any, Any, Any]],
    provider_id: str,
    max_retries: int = 2,
) -> Any:
    """Execute with bounded exponential backoff and jitter for transient errors."""
    attempt = 0
    while True:
        try:
            return await fn()
        except ProviderError as exc:
            attempt += 1
            if not exc.retryable or attempt > max_retries:
                raise
            delay = min(2.0 ** attempt + random.uniform(0.1, 0.5), 10.0)
            if exc.retry_after:
                delay = max(delay, exc.retry_after)
            log.info("Retrying %s (attempt %d/%d) after %.2fs due to %s", provider_id, attempt, max_retries, exc.code)
            await asyncio.sleep(delay)
        except Exception as exc:
            attempt += 1
            if attempt > max_retries:
                raise ProviderError(f"Unexpected error calling {provider_id}: {exc}", code="upstream_error", retryable=False) from exc
            delay = min(2.0 ** attempt + random.uniform(0.1, 0.5), 8.0)
            await asyncio.sleep(delay)


class MultiProviderTranscriber:
    def __init__(self, transcribers: list[tuple[str, Transcriber]], cb: CircuitBreaker, max_retries: int = 2) -> None:
        self.transcribers = transcribers
        self.cb = cb
        self.max_retries = max_retries

    async def transcribe(self, wav: bytes, *, language_bias: Sequence[str] | None = None) -> TranscriptionResult:
        errors = []
        for pid, t in self.transcribers:
            if not self.cb.is_available(pid):
                log.info("Skipping transcriber %s (in cooldown)", pid)
                continue
            try:
                res = await retry_with_backoff(
                    lambda: t.transcribe(wav, language_bias=language_bias),
                    pid,
                    self.max_retries,
                )
                self.cb.record_success(pid)
                return res
            except Exception as exc:
                self.cb.record_failure(pid, exc)
                errors.append(f"{pid}: {exc}")
                log.warning("Transcriber %s failed, attempting fallback: %s", pid, exc)

        raise ProviderError(
            f"Voice transcription failed across all providers ({'; '.join(errors)}). Please type your message.",
            code="transcription_unavailable",
            status=503,
            retryable=False,
        )


class MultiProviderVision:
    def __init__(self, vision_providers: list[tuple[str, VisionAnalyzer]], cb: CircuitBreaker, max_retries: int = 2) -> None:
        self.vision_providers = vision_providers
        self.cb = cb
        self.max_retries = max_retries

    async def analyze(self, frames: Sequence[bytes], *, context: str) -> VisionResult:
        if not frames:
            return VisionResult(observations=[], provider="none")

        errors = []
        for pid, v in self.vision_providers:
            if not self.cb.is_available(pid):
                log.info("Skipping vision provider %s (in cooldown)", pid)
                continue
            try:
                res = await retry_with_backoff(
                    lambda: v.analyze(frames, context=context),
                    pid,
                    self.max_retries,
                )
                self.cb.record_success(pid)
                return res
            except Exception as exc:
                self.cb.record_failure(pid, exc)
                errors.append(f"{pid}: {exc}")
                log.warning("Vision provider %s failed, attempting fallback: %s", pid, exc)

        log.error("All vision providers failed: %s", "; ".join(errors))
        return VisionResult(
            observations=[],
            provider="fallback:unusable",
            image_quality="unusable",
            needs_closer_view=True,
        )


class MultiProviderReasoner:
    def __init__(
        self,
        reasoners: list[tuple[str, Reasoner]],
        cb: CircuitBreaker,
        fallback_reasoner: Reasoner | None = None,
        max_retries: int = 2,
    ) -> None:
        self.reasoners = reasoners
        self.cb = cb
        self.fallback = fallback_reasoner or SafeDeterministicFallbackReasoner()
        self.max_retries = max_retries

    async def reason(
        self,
        *,
        system: str,
        history: list[dict[str, str]],
        user_text: str,
        vision: VisionResult | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        errors = []
        for pid, r in self.reasoners:
            if not self.cb.is_available(pid):
                log.info("Skipping reasoner %s (in cooldown)", pid)
                continue
            try:
                raw = await retry_with_backoff(
                    lambda: r.reason(
                        system=system,
                        history=history,
                        user_text=user_text,
                        vision=vision,
                        context=context,
                    ),
                    pid,
                    self.max_retries,
                )
                self.cb.record_success(pid)
                if isinstance(raw, dict):
                    raw["_provider"] = pid
                return raw
            except Exception as exc:
                self.cb.record_failure(pid, exc)
                errors.append(f"{pid}: {exc}")
                log.warning("Reasoner %s failed, falling back to next provider: %s", pid, exc)

        log.warning("All primary reasoners failed (%s). Engaging safe deterministic fallback.", "; ".join(errors))
        fallback_raw = await self.fallback.reason(
            system=system,
            history=history,
            user_text=user_text,
            vision=vision,
            context=context,
        )
        if isinstance(fallback_raw, dict):
            fallback_raw["_provider"] = "deterministic_fallback"
            fallback_raw["_fallback_reason"] = "; ".join(errors)
        return fallback_raw

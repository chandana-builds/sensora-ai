"""Groq API provider (https://api.groq.com/openai/v1, Bearer GROQ_API_KEY).

Provides speech-to-text (whisper-large-v3), vision (llama-3.2-11b-vision-preview),
and fast reasoning (llama-3.3-70b-versatile).
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any, Sequence

import httpx

from .base import ProviderError, ProviderNotConfigured, TranscriptionResult, VisionResult
from .config import AISettings
from .meta_provider import VISION_PROMPT, extract_json

log = logging.getLogger("sensora.ai.groq")


class _GroqHttp:
    def __init__(self, s: AISettings, client: httpx.AsyncClient | None = None) -> None:
        if not s.groq_api_key:
            raise ProviderNotConfigured("GROQ_API_KEY is not set; cannot use the Groq provider.")
        self.s, self._client = s, client
        self._headers = {"Authorization": f"Bearer {s.groq_api_key}"}

    async def post(self, path: str, **kw: Any) -> dict[str, Any]:
        url = f"{self.s.groq_base_url}{path}"
        try:
            if self._client:
                resp = await self._client.post(url, headers=self._headers, **kw)
            else:
                async with httpx.AsyncClient(timeout=self.s.timeout_s) as c:
                    resp = await c.post(url, headers=self._headers, **kw)
        except httpx.TimeoutException as exc:
            raise ProviderError("The Groq service timed out.", code="timeout", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Could not reach the Groq service.", code="network_error", retryable=True) from exc

        if resp.status_code >= 400:
            self._raise(resp, path)

        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError("Groq returned a non-JSON response.", code="bad_response") from exc

    @staticmethod
    def _raise(resp: httpx.Response, path: str) -> None:
        sc = resp.status_code
        log.warning("Groq API %s -> HTTP %s", path, sc)
        if sc in (401, 403):
            raise ProviderError("The Groq API key was rejected or invalid.", code="auth_failed", status=sc)
        if sc == 404:
            raise ProviderError("Groq model or endpoint not found.", code="model_unavailable", status=sc)
        if sc == 429:
            ra = resp.headers.get("Retry-After", "")
            raise ProviderError("Groq rate limit reached. Try again shortly.", code="rate_limited", status=sc,
                                retryable=True, retry_after=float(ra) if ra.isdigit() else None)
        if sc >= 500:
            raise ProviderError("Groq service experienced an internal error.", code="upstream_error", status=sc, retryable=True)
        raise ProviderError(f"Groq request rejected (HTTP {sc}).", code="bad_request", status=sc)


def _content(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("Unexpected Groq response structure.", code="bad_response") from exc
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


class GroqTranscriber:
    name = "groq:whisper"

    def __init__(self, s: AISettings, client: httpx.AsyncClient | None = None) -> None:
        self.http, self.s = _GroqHttp(s, client), s

    async def transcribe(self, wav: bytes, *, language_bias: Sequence[str] | None = None) -> TranscriptionResult:
        files = {
            "file": ("audio.wav", wav, "audio/wav"),
        }
        data = {
            "model": self.s.groq_stt_model,
            "response_format": "json",
        }
        res = await self.http.post("/audio/transcriptions", files=files, data=data)
        text = res.get("text", "").strip()
        return TranscriptionResult(text=text, provider=self.name)


class GroqVision:
    name = "groq:vision"

    def __init__(self, s: AISettings, client: httpx.AsyncClient | None = None) -> None:
        self.http, self.s = _GroqHttp(s, client), s

    async def analyze(self, frames: Sequence[bytes], *, context: str) -> VisionResult:
        parts: list[dict[str, Any]] = [{"type": "text", "text": f"Context: {context}"}]
        for f in frames:
            parts.append({
                "type": "image_url",
                "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(f).decode()},
            })

        payload = {
            "model": self.s.groq_vision_model,
            "messages": [
                {"role": "system", "content": VISION_PROMPT},
                {"role": "user", "content": parts},
            ],
            "temperature": 0.2,
            "max_tokens": 600,
        }
        data = await self.http.post("/chat/completions", json=payload)
        obj = extract_json(_content(data))
        quality = obj.get("image_quality", "good")
        return VisionResult(
            observations=[str(o) for o in obj.get("observations", [])][:12],
            device_guess=obj.get("device_guess") or None,
            visible_text=[str(o) for o in obj.get("visible_text", [])][:10],
            image_quality=quality if quality in ("good", "poor", "unusable") else "poor",
            needs_closer_view=bool(obj.get("needs_closer_view", False)),
            provider=self.name,
        )


class GroqReasoner:
    name = "groq:reasoner"

    def __init__(self, s: AISettings, client: httpx.AsyncClient | None = None) -> None:
        self.http, self.s = _GroqHttp(s, client), s

    async def reason(self, *, system: str, history: list[dict[str, str]], user_text: str, vision: VisionResult | None, context: dict[str, Any]) -> dict[str, Any]:
        evidence = "No image was sent this turn."
        if vision:
            evidence = "Vision analysis of the frame(s) sent this turn: " + json.dumps({
                "observations": vision.observations,
                "device_guess": vision.device_guess,
                "visible_text": vision.visible_text,
                "image_quality": vision.image_quality,
                "needs_closer_view": vision.needs_closer_view,
            })
        user = f"{user_text}\n\n[EVIDENCE]\n{evidence}\n[SESSION]\n{json.dumps(context)}"
        msgs = [{"role": "system", "content": system}, *history, {"role": "user", "content": user}]

        payload = {
            "model": self.s.groq_reasoning_model,
            "messages": msgs,
            "temperature": 0.2,
            "max_tokens": 1000,
            "response_format": {"type": "json_object"},
        }
        data = await self.http.post("/chat/completions", json=payload)
        return extract_json(_content(data))

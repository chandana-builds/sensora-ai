"""Google Gemini API provider (https://generativelanguage.googleapis.com/v1beta, key=GEMINI_API_KEY).

Provides visual analysis (GeminiVision) and troubleshooting reasoning (GeminiReasoner)
using the Gemini REST API (gemini-1.5-flash / gemini-2.0-flash).
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any, Sequence

import httpx

from .base import ProviderError, ProviderNotConfigured, VisionResult
from .config import AISettings
from .meta_provider import VISION_PROMPT, extract_json

log = logging.getLogger("sensora.ai.gemini")


class _GeminiHttp:
    def __init__(self, s: AISettings, client: httpx.AsyncClient | None = None) -> None:
        if not s.gemini_api_key:
            raise ProviderNotConfigured("GEMINI_API_KEY is not set; cannot use the Gemini provider.")
        self.s, self._client = s, client
        self.key = s.gemini_api_key

    async def generate_content(self, model: str, contents: list[dict[str, Any]], system_instruction: str | None = None) -> dict[str, Any]:
        url = f"{self.s.gemini_base_url}/models/{model}:generateContent?key={self.key}"
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1024,
                "responseMimeType": "application/json",
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        headers = {"Content-Type": "application/json"}
        try:
            if self._client:
                resp = await self._client.post(url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self.s.timeout_s) as c:
                    resp = await c.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError("The Gemini service timed out.", code="timeout", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Could not reach the Gemini service.", code="network_error", retryable=True) from exc

        if resp.status_code >= 400:
            self._raise(resp)

        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError("Gemini returned a non-JSON response.", code="bad_response") from exc

    @staticmethod
    def _raise(resp: httpx.Response) -> None:
        sc = resp.status_code
        log.warning("Gemini API -> HTTP %s", sc)
        if sc in (401, 403):
            raise ProviderError("The Gemini API key was rejected or lacks permissions.", code="auth_failed", status=sc)
        if sc == 404:
            raise ProviderError("Gemini model or endpoint not found.", code="model_unavailable", status=sc)
        if sc == 429:
            ra = resp.headers.get("Retry-After", "")
            raise ProviderError("Gemini rate limit or quota reached. Try again shortly.", code="rate_limited", status=sc,
                                retryable=True, retry_after=float(ra) if ra.isdigit() else None)
        if sc >= 500:
            raise ProviderError("Gemini service had an internal or capacity error.", code="upstream_error", status=sc, retryable=True)
        raise ProviderError(f"Gemini request rejected (HTTP {sc}).", code="bad_request", status=sc)


def _extract_gemini_text(data: dict[str, Any]) -> str:
    try:
        candidates = data.get("candidates", [])
        if not candidates:
            feedback = data.get("promptFeedback", {})
            block_reason = feedback.get("blockReason", "unknown")
            raise ProviderError(f"Gemini response blocked ({block_reason}).", code="safety_blocked")
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("Unexpected Gemini response shape.", code="bad_response") from exc


class GeminiVision:
    name = "gemini:vision"

    def __init__(self, s: AISettings, client: httpx.AsyncClient | None = None) -> None:
        self.http, self.s = _GeminiHttp(s, client), s

    async def analyze(self, frames: Sequence[bytes], *, context: str) -> VisionResult:
        parts: list[dict[str, Any]] = [{"text": f"Context: {context}\nInstructions: {VISION_PROMPT}"}]
        for f in frames:
            parts.append({
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": base64.b64encode(f).decode(),
                }
            })

        contents = [{"role": "user", "parts": parts}]
        data = await self.http.generate_content(
            self.s.gemini_model,
            contents,
            system_instruction="You inspect device photos for an assistant. Return factual JSON only.",
        )
        text = _extract_gemini_text(data)
        obj = extract_json(text)
        quality = obj.get("image_quality", "good")
        return VisionResult(
            observations=[str(o) for o in obj.get("observations", [])][:12],
            device_guess=obj.get("device_guess") or None,
            visible_text=[str(o) for o in obj.get("visible_text", [])][:10],
            image_quality=quality if quality in ("good", "poor", "unusable") else "poor",
            needs_closer_view=bool(obj.get("needs_closer_view", False)),
            provider=self.name,
        )


class GeminiReasoner:
    name = "gemini:reasoner"

    def __init__(self, s: AISettings, client: httpx.AsyncClient | None = None) -> None:
        self.http, self.s = _GeminiHttp(s, client), s

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

        user_content = f"{user_text}\n\n[EVIDENCE]\n{evidence}\n[SESSION]\n{json.dumps(context)}"

        contents = []
        for m in history:
            role = "model" if m.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
        contents.append({"role": "user", "parts": [{"text": user_content}]})

        data = await self.http.generate_content(
            self.s.gemini_model,
            contents,
            system_instruction=system,
        )
        text = _extract_gemini_text(data)
        return extract_json(text)

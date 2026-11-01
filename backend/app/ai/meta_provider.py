"""Meta Model API provider (https://api.meta.ai/v1, Bearer MODEL_API_KEY).

Checked against dev.meta.ai docs: OpenAI-compatible POST /chat/completions with image_url
data-URL parts (model muse-spark-1.3), and POST /asr/transcribe (multipart: JSON `request`
part + WAV `audio` part, model muse-voice-transcribe-1.0, mono 16-bit 16/24 kHz WAV).
"""
from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any, Sequence

import httpx

from .base import ProviderError, ProviderNotConfigured, TranscriptionResult, VisionResult
from .config import AISettings

log = logging.getLogger("sensora.ai.meta")


def extract_json(text: str) -> dict[str, Any]:
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    candidates = [t]
    if "{" in t and "}" in t:
        candidates.append(t[t.find("{"): t.rfind("}") + 1])
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    raise ProviderError("Model did not return valid JSON", code="invalid_model_output")


class _Http:
    def __init__(self, s: AISettings, client: httpx.AsyncClient | None = None) -> None:
        if not s.api_key:
            raise ProviderNotConfigured("MODEL_API_KEY is not set; cannot use the Meta provider.")
        self.s, self._client = s, client
        self._headers = {"Authorization": f"Bearer {s.api_key}"}

    async def post(self, path: str, **kw: Any) -> dict[str, Any]:
        url = f"{self.s.base_url}{path}"
        try:
            if self._client:
                resp = await self._client.post(url, headers=self._headers, **kw)
            else:
                async with httpx.AsyncClient(timeout=self.s.timeout_s) as c:
                    resp = await c.post(url, headers=self._headers, **kw)
        except httpx.TimeoutException as exc:
            raise ProviderError("The AI service timed out.", code="timeout", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Could not reach the AI service.", code="network_error", retryable=True) from exc
        if resp.status_code >= 400:
            self._raise(resp, path)
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError("AI service returned a non-JSON response.", code="bad_response") from exc

    @staticmethod
    def _raise(resp: httpx.Response, path: str) -> None:
        sc = resp.status_code
        log.warning("Meta API %s -> HTTP %s", path, sc)  # never log bodies, keys or images
        if sc in (401, 403):
            raise ProviderError("The AI API key was rejected or lacks access.", code="auth_failed", status=sc)
        if sc == 404:
            raise ProviderError("Model or endpoint not available to this key.", code="model_unavailable", status=sc)
        if sc == 429:
            ra = resp.headers.get("Retry-After", "")
            raise ProviderError("AI rate limit reached. Try again shortly.", code="rate_limited", status=sc,
                                retryable=True, retry_after=float(ra) if ra.isdigit() else None)
        if sc >= 500:
            raise ProviderError("The AI service had an internal error.", code="upstream_error", status=sc, retryable=True)
        raise ProviderError(f"AI request rejected (HTTP {sc}).", code="bad_request", status=sc)


class MetaTranscriber:
    name = "meta:muse-voice-transcribe"

    def __init__(self, s: AISettings, client: httpx.AsyncClient | None = None) -> None:
        self.http, self.s = _Http(s, client), s

    async def transcribe(self, wav: bytes, *, language_bias: Sequence[str] | None = None) -> TranscriptionResult:
        req: dict[str, Any] = {"model": self.s.stt_model, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK"}
        bias = list(language_bias or self.s.stt_language_bias)
        if bias:
            req["languageBias"] = bias  # language NAMES, e.g. "English"
        data = await self.http.post("/asr/transcribe", files={
            "request": (None, json.dumps(req), "application/json"),
            "audio": ("audio.wav", wav, "audio/wav"),
        })
        text = data.get("transcript") or data.get("text") or " ".join(
            t.get("text", "") for t in data.get("turns", []) if isinstance(t, dict))
        return TranscriptionResult(text=text.strip(), provider=self.name)


def _chat_payload(s: AISettings, model: str, messages: list[dict[str, Any]],
                  max_tokens: int, schema: dict | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}
    if schema and s.use_json_schema:  # opt-in: exact response_format shape not confirmed for this API
        payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "response", "schema": schema}}
    return payload


def _content(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("Unexpected AI response shape.", code="bad_response") from exc
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


VISION_PROMPT = (
    "You inspect photos of a household device for a troubleshooting assistant. Report ONLY what is "
    "visible. Never guess hidden internals. Reply with JSON only: "
    '{"observations": [short factual strings], "device_guess": string|null, '
    '"visible_text": [model numbers/error codes/labels you can actually read], '
    '"image_quality": "good"|"poor"|"unusable", "needs_closer_view": boolean}. '
    "If the image is blurry, dark or does not show a device, say so via image_quality."
)


class MetaVision:
    name = "meta:muse-spark"

    def __init__(self, s: AISettings, client: httpx.AsyncClient | None = None) -> None:
        self.http, self.s = _Http(s, client), s

    async def analyze(self, frames: Sequence[bytes], *, context: str) -> VisionResult:
        parts: list[dict[str, Any]] = [{"type": "text", "text": f"Context from the user: {context}"}]
        for f in frames:
            parts.append({"type": "image_url",
                          "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(f).decode()}})
        data = await self.http.post("/chat/completions", json=_chat_payload(
            self.s, self.s.vision_model,
            [{"role": "system", "content": VISION_PROMPT}, {"role": "user", "content": parts}], 600, None))
        obj = extract_json(_content(data))
        quality = obj.get("image_quality", "good")
        return VisionResult(
            observations=[str(o) for o in obj.get("observations", [])][:12],
            device_guess=obj.get("device_guess") or None,
            visible_text=[str(o) for o in obj.get("visible_text", [])][:10],
            image_quality=quality if quality in ("good", "poor", "unusable") else "poor",
            needs_closer_view=bool(obj.get("needs_closer_view", False)),
            provider=self.name)


class MetaReasoner:
    name = "meta:muse-spark"

    def __init__(self, s: AISettings, client: httpx.AsyncClient | None = None) -> None:
        self.http, self.s = _Http(s, client), s

    async def reason(self, *, system, history, user_text, vision, context) -> dict[str, Any]:
        from ..schemas_ai import TroubleshootingResponse
        evidence = "No image was sent this turn."
        if vision:
            evidence = "Vision analysis of the frame(s) sent this turn: " + json.dumps({
                "observations": vision.observations, "device_guess": vision.device_guess,
                "visible_text": vision.visible_text, "image_quality": vision.image_quality,
                "needs_closer_view": vision.needs_closer_view})
        user = f"{user_text}\n\n[EVIDENCE]\n{evidence}\n[SESSION]\n{json.dumps(context)}"
        msgs = [{"role": "system", "content": system}, *history, {"role": "user", "content": user}]
        data = await self.http.post("/chat/completions", json=_chat_payload(
            self.s, self.s.reasoning_model, msgs, 900, TroubleshootingResponse.model_json_schema()))
        return extract_json(_content(data))

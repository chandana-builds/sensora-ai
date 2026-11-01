"""Voice + AI status routes: GET /ai/status (public), POST /transcribe (auth + daily quota)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from ..ai.base import ProviderError, ProviderNotConfigured
from ..ai.config import load_ai_settings
from ..ai.demo_provider_v3 import build_providers_v3
from ..ai.factory import Providers
from ..deps import user_with_quota
from ..schemas_ai import AIStatus, TranscribeResponse
from ..services.audio import MAX_BYTES, AudioError, validate_wav

log = logging.getLogger("sensora.live")
router = APIRouter(tags=["live"])


def _providers(request: Request) -> Providers:
    p = getattr(request.app.state, "ai_providers_v3", None)
    if p is None:
        try:
            p = build_providers_v3(load_ai_settings())
        except ProviderNotConfigured as exc:
            raise HTTPException(503, exc.message) from exc
        request.app.state.ai_providers_v3 = p
    return p


def _http(exc: ProviderError) -> HTTPException:
    status = {"rate_limited": 429, "timeout": 504, "auth_failed": 502, "model_unavailable": 502,
              "not_configured": 503, "demo_no_stt": 503}.get(exc.code, exc.status if exc.status and exc.status >= 500 else 502)
    headers = {"Retry-After": str(int(exc.retry_after))} if exc.retry_after else None
    return HTTPException(status, {"code": exc.code, "message": exc.message, "retryable": exc.retryable}, headers=headers)


@router.get("/ai/status", response_model=AIStatus)
async def ai_status(request: Request) -> AIStatus:
    s = load_ai_settings()
    mode = s.effective_mode
    if mode == "demo":
        return AIStatus(
            mode="demo",
            simulated=True,
            transcription="unavailable in demo mode",
            vision="simulated (canned, ignores the image)",
            reasoning=f"simulated scenario: {s.demo_scenario}",
            note="DEMO MODE: responses are scripted, not Meta model output.",
            providers=["demo"],
            provider_status={"demo": "active"},
        )
    ok = bool(s.api_key or s.gemini_api_key or s.groq_api_key)
    cb_status = {}
    p = getattr(request.app.state, "ai_providers_v3", None)
    if p and hasattr(p.reasoner, "cb"):
        cb = p.reasoner.cb
        for name in s.provider_order:
            if name in cb.auth_disabled:
                cb_status[name] = "auth_disabled"
            elif cb.is_cooling_down(name):
                cb_status[name] = "cooling_down"
            else:
                cb_status[name] = "healthy"
    else:
        for name in s.provider_order:
            has_k = (name == "meta" and bool(s.api_key)) or (name == "gemini" and bool(s.gemini_api_key)) or (name == "groq" and bool(s.groq_api_key))
            cb_status[name] = "configured" if has_k else "missing_key"

    return AIStatus(
        mode="real",
        simulated=False,
        transcription=f"{s.stt_model} (groq fallback: {s.groq_stt_model})" if (s.api_key or s.groq_api_key) else "not configured",
        vision=f"{s.vision_model} (fallbacks: {s.gemini_model}, {s.groq_vision_model})",
        reasoning=f"{s.reasoning_model} (fallbacks: {s.gemini_model}, {s.groq_reasoning_model})",
        note="Configured. Reachability is only confirmed by a real call." if ok else "No AI provider keys configured.",
        providers=s.provider_order,
        provider_status=cb_status,
    )



@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(audio: UploadFile, request: Request, cid: str = Depends(user_with_quota)) -> TranscribeResponse:
    data = await audio.read(MAX_BYTES + 1)
    try:
        validate_wav(data)
    except AudioError as exc:
        raise HTTPException(422, str(exc))
    p = _providers(request)
    try:
        r = await p.transcriber.transcribe(data)
    except ProviderError as exc:
        raise _http(exc)
    if not r.text:
        raise HTTPException(422, "No speech detected. Try again closer to the microphone.")
    return TranscribeResponse(text=r.text, provider=r.provider, simulated=r.simulated)

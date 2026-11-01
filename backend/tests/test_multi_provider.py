"""Tests for Sensora AI Multi-Provider AI Reliability Architecture.
Verifies Meta, Google Gemini, and Groq adapters, ordered fallback routing,
circuit breaker cooldowns, vision capability routing, STT fallback,
safety enforcement, and deterministic fallback.
"""
import base64
import json
import httpx
import pytest

from app.ai.base import ProviderError, VisionResult
from app.ai.config import load_ai_settings
from app.ai.gemini_provider import GeminiReasoner, GeminiVision
from app.ai.groq_provider import GroqReasoner, GroqTranscriber, GroqVision
from app.ai.meta_provider import MetaReasoner, MetaTranscriber, MetaVision
from app.ai.router import (
    CircuitBreaker,
    MultiProviderReasoner,
    MultiProviderTranscriber,
    MultiProviderVision,
    SafeDeterministicFallbackReasoner,
)
from app.schemas_ai import TroubleshootingResponse
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.memory_store import InMemoryMemoryStore


# Valid test payloads
VALID_TROUBLESHOOTING_JSON = {
    "assistant_message": "Please inspect the power cable for any visible tears.",
    "observations": ["power LED is off"],
    "likely_causes": [{"cause": "Disconnected power", "likelihood": "high"}],
    "confidence": {"level": "high", "note": "Clear symptom"},
    "current_step": {
        "title": "Check power connection",
        "instruction": "Ensure the power cord is firmly seated in the wall outlet.",
        "expected_result": "Power LED turns on",
    },
    "requested_user_action": "Ensure the power cord is firmly seated in the wall outlet.",
    "requires_new_image": False,
    "verification_required": True,
    "safety_status": "ok",
    "escalation_recommended": False,
}

VALID_VISION_JSON = {
    "observations": ["Loose connection at socket", "LED unlit"],
    "image_quality": "good",
    "confidence": 0.92,
}


def make_test_settings(**overrides):
    env = {
        "AI_MODE": "real",
        "MODEL_API_KEY": "meta-test-key",
        "GEMINI_API_KEY": "gemini-test-key",
        "GROQ_API_KEY": "groq-test-key",
        "AI_PROVIDER_ORDER": "meta,gemini,groq",
        "AI_MAX_RETRIES": "1",
        "AI_COOLDOWN_SECONDS": "60",
    }
    env.update(overrides)
    return load_ai_settings(env)


# ============================================================================
# 1. Individual Provider Adapter Tests (Gemini & Groq)
# ============================================================================

async def test_gemini_vision_and_reasoner_success():
    """Verify Gemini multimodal payload structure and response normalization."""
    settings = make_test_settings()
    vision_called = False
    reason_called = False

    def handler(req: httpx.Request):
        nonlocal vision_called, reason_called
        body = json.loads(req.content)
        assert "key=gemini-test-key" in str(req.url)

        if "analyze" in str(req.url) or not reason_called:
            vision_called = True
            # Verify inlineData part for image
            parts = body["contents"][0]["parts"]
            assert any("inlineData" in p for p in parts)
            resp_body = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(VALID_VISION_JSON)
                                }
                            ]
                        }
                    }
                ]
            }
            return httpx.Response(200, json=resp_body)
        else:
            reason_called = True
            # Verify systemInstruction
            assert "systemInstruction" in body
            resp_body = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(VALID_TROUBLESHOOTING_JSON)
                                }
                            ]
                        }
                    }
                ]
            }
            return httpx.Response(200, json=resp_body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gv = GeminiVision(settings, client)
    vis_res = await gv.analyze([b"\xff\xd8\xff\xe0testimage"], context="refrigerator")
    assert vis_res.image_quality == "good"
    assert "LED unlit" in vis_res.observations

    reason_called = True
    gr = GeminiReasoner(settings, client)
    res = await gr.reason(
        system="System prompt",
        history=[{"role": "user", "content": "Fridge not cooling"}],
        user_text="What do I do?",
        vision=vis_res,
        context={},
    )
    assert res["assistant_message"] == VALID_TROUBLESHOOTING_JSON["assistant_message"]
    assert res["safety_status"] == "ok"


async def test_gemini_error_mapping():
    """Verify Gemini API errors are mapped to Sensora ProviderError codes."""
    settings = make_test_settings()

    for code, expected_code, retryable in [
        (401, "auth_failed", False),
        (403, "auth_failed", False),
        (429, "rate_limited", True),
        (503, "upstream_error", True),
    ]:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req, c=code: httpx.Response(c, json={"error": {"message": "err"}}))
        )
        gr = GeminiReasoner(settings, client)
        with pytest.raises(ProviderError) as exc_info:
            await gr.reason(system="sys", history=[], user_text="hi", vision=None, context={})
        assert exc_info.value.code == expected_code
        assert exc_info.value.retryable == retryable


async def test_groq_vision_reasoner_and_stt():
    """Verify Groq OpenAI-compatible payload structure and Whisper STT."""
    settings = make_test_settings()

    def handler(req: httpx.Request):
        assert req.headers["authorization"] == "Bearer groq-test-key"
        if req.url.path.endswith("/audio/transcriptions"):
            assert "multipart/form-data" in req.headers.get("content-type", "")
            return httpx.Response(200, json={"text": "transcribed speech from groq"})

        body = json.loads(req.content)
        if body["model"] == settings.groq_vision_model:
            content = json.dumps(VALID_VISION_JSON)
        else:
            content = json.dumps(VALID_TROUBLESHOOTING_JSON)

        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # STT
    gt = GroqTranscriber(settings, client)
    stt_res = await gt.transcribe(b"RIFF....fake-wav-data")
    assert stt_res.text == "transcribed speech from groq"
    assert stt_res.provider.startswith("groq")

    # Vision
    gv = GroqVision(settings, client)
    vis = await gv.analyze([b"\xff\xd8\xff\xe0test"], context="test")
    assert vis.image_quality == "good"

    # Reasoner
    gr = GroqReasoner(settings, client)
    reason = await gr.reason(system="s", history=[], user_text="text", vision=vis, context={})
    assert reason["assistant_message"] == VALID_TROUBLESHOOTING_JSON["assistant_message"]


# ============================================================================
# 2. Ordered Fallback Routing & Failure Handling Tests
# ============================================================================

async def test_primary_meta_success():
    """When Meta succeeds, no fallback providers are called."""
    settings = make_test_settings()
    calls = []

    def meta_handler(req: httpx.Request):
        calls.append("meta")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(VALID_TROUBLESHOOTING_JSON)}}]})

    def gemini_handler(req: httpx.Request):
        calls.append("gemini")
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(VALID_TROUBLESHOOTING_JSON)}]}}]})

    meta_c = httpx.AsyncClient(transport=httpx.MockTransport(meta_handler))
    gemini_c = httpx.AsyncClient(transport=httpx.MockTransport(gemini_handler))

    cb = CircuitBreaker()
    providers = [
        ("meta", MetaReasoner(settings, meta_c)),
        ("gemini", GeminiReasoner(settings, gemini_c)),
    ]
    router = MultiProviderReasoner(providers, cb, max_retries=1)

    res = await router.reason(system="s", history=[], user_text="help", vision=None, context={})
    assert res["_provider"] == "meta"
    assert calls == ["meta"]


async def test_fallback_to_gemini_when_meta_fails():
    """When Meta returns 503/timeout, fallback to Gemini succeeds seamlessly."""
    settings = make_test_settings()
    calls = []

    def meta_handler(req: httpx.Request):
        calls.append("meta")
        return httpx.Response(503, json={"error": "service unavailable"})

    def gemini_handler(req: httpx.Request):
        calls.append("gemini")
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(VALID_TROUBLESHOOTING_JSON)}]}}]},
        )

    meta_c = httpx.AsyncClient(transport=httpx.MockTransport(meta_handler))
    gemini_c = httpx.AsyncClient(transport=httpx.MockTransport(gemini_handler))

    cb = CircuitBreaker()
    providers = [
        ("meta", MetaReasoner(settings, meta_c)),
        ("gemini", GeminiReasoner(settings, gemini_c)),
    ]
    router = MultiProviderReasoner(providers, cb, max_retries=0)

    res = await router.reason(system="s", history=[], user_text="help", vision=None, context={})
    assert res["_provider"] == "gemini"
    assert "meta" in calls and "gemini" in calls


async def test_fallback_to_groq_when_meta_and_gemini_fail():
    """When Meta and Gemini both fail, fallback to Groq succeeds."""
    settings = make_test_settings()
    calls = []

    def meta_handler(req: httpx.Request):
        calls.append("meta")
        return httpx.Response(500, json={"error": "meta server error"})

    def gemini_handler(req: httpx.Request):
        calls.append("gemini")
        return httpx.Response(500, json={"error": "gemini server error"})

    def groq_handler(req: httpx.Request):
        calls.append("groq")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(VALID_TROUBLESHOOTING_JSON)}}]})

    cb = CircuitBreaker()
    providers = [
        ("meta", MetaReasoner(settings, httpx.AsyncClient(transport=httpx.MockTransport(meta_handler)))),
        ("gemini", GeminiReasoner(settings, httpx.AsyncClient(transport=httpx.MockTransport(gemini_handler)))),
        ("groq", GroqReasoner(settings, httpx.AsyncClient(transport=httpx.MockTransport(groq_handler)))),
    ]
    router = MultiProviderReasoner(providers, cb, max_retries=0)

    res = await router.reason(system="s", history=[], user_text="help", vision=None, context={})
    assert res["_provider"] == "groq"
    assert calls == ["meta", "gemini", "groq"]


async def test_transcription_fallback_to_groq():
    """When Meta STT fails with 503, Groq Whisper STT is automatically used."""
    settings = make_test_settings()
    calls = []

    def meta_handler(req: httpx.Request):
        calls.append("meta")
        return httpx.Response(503, json={"error": "speech service down"})

    def groq_handler(req: httpx.Request):
        calls.append("groq")
        return httpx.Response(200, json={"text": "audio transcribed via groq whisper"})

    cb = CircuitBreaker()
    providers = [
        ("meta", MetaTranscriber(settings, httpx.AsyncClient(transport=httpx.MockTransport(meta_handler)))),
        ("groq", GroqTranscriber(settings, httpx.AsyncClient(transport=httpx.MockTransport(groq_handler)))),
    ]
    router = MultiProviderTranscriber(providers, cb, max_retries=0)

    res = await router.transcribe(b"RIFF....wav")
    assert res.provider.startswith("groq")
    assert res.text == "audio transcribed via groq whisper"
    assert calls == ["meta", "groq"]


async def test_vision_capability_routing():
    """Router only attempts providers that support vision."""
    settings = make_test_settings()
    calls = []

    def meta_handler(req: httpx.Request):
        calls.append("meta")
        return httpx.Response(500)

    def groq_handler(req: httpx.Request):
        calls.append("groq")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(VALID_VISION_JSON)}}]})

    cb = CircuitBreaker()
    providers = [
        ("meta", MetaVision(settings, httpx.AsyncClient(transport=httpx.MockTransport(meta_handler)))),
        ("groq", GroqVision(settings, httpx.AsyncClient(transport=httpx.MockTransport(groq_handler)))),
    ]
    router = MultiProviderVision(providers, cb, max_retries=0)

    res = await router.analyze([b"\xff\xd8\xff\xe0test"], context="device inspection")
    assert res.image_quality == "good"
    assert calls == ["meta", "groq"]


# ============================================================================
# 3. Circuit Breaker, Cooldown, and Auth Failure Tests
# ============================================================================

def test_circuit_breaker_cooldown():
    """Tripping circuit breaker marks provider cooling down and skips subsequent calls."""
    cb = CircuitBreaker(default_cooldown_s=60.0, max_consecutive_failures=2)
    assert cb.is_available("meta")

    # 1st failure: still available
    cb.record_failure("meta")
    assert cb.is_available("meta")
    assert not cb.is_cooling_down("meta")

    # 2nd failure: trips into cooldown
    cb.record_failure("meta")
    assert not cb.is_available("meta")
    assert cb.is_cooling_down("meta")

    # Success on another provider resets its count
    cb.record_failure("gemini")
    cb.record_success("gemini")
    assert cb.is_available("gemini")


def test_auth_error_permanently_disables_without_retry():
    """Auth failures (401/403) immediately disable provider without backoff retries."""
    cb = CircuitBreaker()
    err = ProviderError("Invalid API key", code="auth_failed", status=401, retryable=False)
    cb.record_failure("gemini", err)

    assert not cb.is_available("gemini")
    assert "gemini" in cb.auth_disabled


async def test_rate_limit_retry_after():
    """Rate limit 429 response parses Retry-After header and maps to retryable ProviderError."""
    settings = make_test_settings()

    def handler(req: httpx.Request):
        return httpx.Response(429, headers={"Retry-After": "5"}, json={"error": "Too Many Requests"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gr = GroqReasoner(settings, client)

    with pytest.raises(ProviderError) as exc_info:
        await gr.reason(system="s", history=[], user_text="hi", vision=None, context={})

    assert exc_info.value.code == "rate_limited"
    assert exc_info.value.retryable is True
    assert exc_info.value.retry_after == 5.0


# ============================================================================
# 4. Total Provider Failure & Safe Deterministic Fallback
# ============================================================================

async def test_total_provider_failure_returns_safe_fallback():
    """When all providers fail, session is preserved and clear safe deterministic fallback is returned."""
    settings = make_test_settings()

    def fail_handler(req: httpx.Request):
        return httpx.Response(500, json={"error": "outage"})

    cb = CircuitBreaker()
    providers = [
        ("meta", MetaReasoner(settings, httpx.AsyncClient(transport=httpx.MockTransport(fail_handler)))),
        ("gemini", GeminiReasoner(settings, httpx.AsyncClient(transport=httpx.MockTransport(fail_handler)))),
        ("groq", GroqReasoner(settings, httpx.AsyncClient(transport=httpx.MockTransport(fail_handler)))),
    ]
    router = MultiProviderReasoner(providers, cb, max_retries=0)

    res = await router.reason(system="s", history=[], user_text="Device won't power on", vision=None, context={})

    assert res["_provider"] == "deterministic_fallback"
    assert "Sensora AI is currently operating in safe offline mode" in res["assistant_message"]
    assert res["safety_status"] == "caution"
    assert res["escalation_recommended"] is True

    # Validate schema conforms to TroubleshootingResponse
    parsed = TroubleshootingResponse.model_validate(res)
    assert parsed.assistant_message is not None


async def test_malformed_output_triggers_next_provider():
    """When a provider returns malformed/unparseable JSON, the router falls back to the next provider."""
    settings = make_test_settings()

    def bad_meta_handler(req: httpx.Request):
        # Invalid JSON
        return httpx.Response(200, json={"choices": [{"message": {"content": "I am not returning JSON sorry."}}]})

    def good_gemini_handler(req: httpx.Request):
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(VALID_TROUBLESHOOTING_JSON)}]}}]},
        )

    cb = CircuitBreaker()
    providers = [
        ("meta", MetaReasoner(settings, httpx.AsyncClient(transport=httpx.MockTransport(bad_meta_handler)))),
        ("gemini", GeminiReasoner(settings, httpx.AsyncClient(transport=httpx.MockTransport(good_gemini_handler)))),
    ]
    router = MultiProviderReasoner(providers, cb, max_retries=0)

    res = await router.reason(system="s", history=[], user_text="Need help", vision=None, context={})
    assert res["_provider"] == "gemini"
    assert res["assistant_message"] == VALID_TROUBLESHOOTING_JSON["assistant_message"]


# ============================================================================
# 5. Safety Enforcement on Orchestrator Turn
# ============================================================================

async def test_safety_check_overrides_turn_regardless_of_provider():
    """Hazardous conditions (gas, fire, shock) are intercepted by safety engine before AI providers."""
    store = InMemoryMemoryStore()
    cid = "client-safety-test"
    sid = "sess-001"
    store.create_session(cid, sid, problem="Stove issue")

    # Mock provider that attempts to return advice despite hazard
    class MockHazardousReasoner:
        name = "meta"
        async def reason(self, **kwargs):
            return VALID_TROUBLESHOOTING_JSON

    class DummyProviders:
        mode = "real"
        simulated = False
        transcriber = None
        vision = None
        reasoner = MockHazardousReasoner()

    orch = AgentOrchestrator(store, DummyProviders())

    from types import SimpleNamespace
    req = SimpleNamespace(
        text="I can smell gas near the stove, what should I do?",
        frames=[],
        reported_step_done=False,
        user_level=None,
    )
    turn_res = await orch.handle_turn(cid, sid, req)

    assert turn_res["safety_overridden"] is True
    assert turn_res["workflow_state"] == "escalation_required"
    assert turn_res["provider"] == "deterministic_safety"
    assert "gas" in turn_res["response"]["assistant_message"].lower() or "evacuate" in turn_res["response"]["assistant_message"].lower()
    assert turn_res["response"]["safety_status"] == "stop"

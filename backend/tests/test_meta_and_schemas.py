"""Needs: pip install fastapi pydantic httpx pytest pytest-asyncio  (NOT run in the authoring sandbox)."""
import json

import httpx
import pytest

from app.ai.base import ProviderError
from app.ai.config import load_ai_settings
from app.ai.meta_provider import MetaReasoner, MetaTranscriber, MetaVision, extract_json
from app.schemas_ai import TroubleshootingResponse



def test_schema_stop_clears_step():
    r = TroubleshootingResponse(assistant_message="x", safety_status="stop",
                                current_step={"title": "a", "instruction": "b"})
    assert r.current_step is None and r.escalation_recommended is False and r.requested_user_action is None


def test_extract_json_variants():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": 2} done') == {"a": 2}
    with pytest.raises(ProviderError):
        extract_json("no json")


def settings():
    return load_ai_settings({"MODEL_API_KEY": "test-key"})


async def test_meta_transcribe_request_shape_and_errors():
    seen = {}
    def handler(req: httpx.Request):
        seen["auth"] = req.headers["authorization"]; seen["url"] = str(req.url); seen["body"] = req.content
        return httpx.Response(200, json={"transcript": "hello router"})
    t = MetaTranscriber(settings(), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    r = await t.transcribe(b"RIFF....")
    assert r.text == "hello router" and seen["url"].endswith("/asr/transcribe") and seen["auth"] == "Bearer test-key"
    assert b'"audioEncoding": "WAV"' in seen["body"] and b'"mode": "PUSH_TO_TALK"' in seen["body"]
    for code, expect in [(401, "auth_failed"), (429, "rate_limited"), (500, "upstream_error")]:
        bad = MetaTranscriber(settings(), httpx.AsyncClient(transport=httpx.MockTransport(lambda r, c=code: httpx.Response(c))))
        with pytest.raises(ProviderError) as e:
            await bad.transcribe(b"x")
        assert e.value.code == expect


async def test_meta_vision_and_reasoner_use_image_url_and_parse():
    bodies = []
    def handler(req):
        bodies.append(json.loads(req.content))
        content = ('{"observations":["amber light"],"image_quality":"good"}' if len(bodies) == 1 else
                   '{"assistant_message":"Check power.","confidence":{"level":"low"}}')
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    c = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    v = await MetaVision(settings(), c).analyze([b"\xff\xd8\xff"], context="router")
    assert v.observations == ["amber light"]
    assert bodies[0]["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    raw = await MetaReasoner(settings(), c).reason(system="s", history=[], user_text="hi", vision=v, context={})
    assert TroubleshootingResponse.model_validate(raw).assistant_message == "Check power."

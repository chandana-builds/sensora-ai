"""HTTP-level tests with FastAPI's TestClient. Needs: pip install -r requirements-dev.txt (NOT run in the authoring sandbox)."""
import base64
import io
import wave

import pytest
from fastapi.testclient import TestClient

from app.ai.base import ProviderError
from app.ai.config import load_ai_settings
from app.ai.demo_provider_v3 import build_providers_v3
from app.config import load_settings
from app.main import create_app
from app.security import issue_anon_token

SECRET = "s" * 40
ORIGIN = "https://sensora.example.app"
JPG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 64).decode()


def make(extra=None, providers=None, **kw):
    env = {"APP_SECRET": SECRET, "STORAGE_BACKEND": "memory", "ALLOWED_ORIGINS": ORIGIN, "AI_MODE": "demo", "DEMO_SCENARIO": "router", **(extra or {})}
    app = create_app(load_settings(env), providers_v3=providers or build_providers_v3(load_ai_settings(env)), **kw)
    return app, TestClient(app, raise_server_exceptions=False)


def hdr(token=None):
    return {"Authorization": f"Bearer {token or issue_anon_token(SECRET)}"}


def wav(seconds=1.0, rate=16000):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(b"\x00" * int(seconds * rate) * 2)
    return b.getvalue()


def test_health_live_and_deep():
    _, c = make()
    assert c.get("/api/health/live").json()["status"] == "ok"
    h = c.get("/api/health").json()
    assert h["status"] == "ok" and h["ai"] == {"mode": "demo", "simulated": True, "models_configured": False} and h["storage"]["ok"]
    assert "key" not in str(h).lower().replace("models_configured", "")


def test_all_private_routes_require_auth():
    _, c = make()
    for m, p in [("get", "/api/sessions"), ("post", "/api/sessions"), ("get", "/api/sessions/x"), ("delete", "/api/sessions/x"), ("get", "/api/me/export"),
                 ("delete", "/api/me/data"), ("post", "/api/sessions/x/agent/turn"), ("get", "/api/sessions/x/memory"), ("get", "/api/sessions/x/summary"),
                 ("get", "/api/sessions/x/handoff"), ("post", "/api/sessions/x/handoff/export"), ("put", "/api/sessions/x/consent"),
                 ("delete", "/api/sessions/x/evidence"), ("get", "/api/preferences/experience"), ("post", "/api/transcribe")]:
        assert getattr(c, m)(p).status_code == 401, (m, p)
    assert c.get("/api/sessions", headers={"Authorization": "Bearer anon.AAAAAAAAAAAAAAAAAAAAAA.forged"}).status_code == 401


def test_guest_token_flow_and_disabled_guest():
    _, c = make()
    t = c.post("/api/auth/guest").json()["token"]
    assert c.get("/api/auth/me", headers=hdr(t)).json()["kind"] == "guest"
    _, c2 = make({"ALLOW_ANONYMOUS_DEMO": "false", "SUPABASE_URL": "https://x.supabase.co", "SUPABASE_ANON_KEY": "a"})
    assert c2.post("/api/auth/guest").status_code == 403 and c2.get("/api/sessions", headers=hdr(t)).status_code == 401


def test_session_ownership_isolation():
    _, c = make()
    alice, bob = hdr(), hdr()
    sid = c.post("/api/sessions", json={"title": "Alice router"}, headers=alice).json()["id"]
    for m, p in [("get", f"/api/sessions/{sid}"), ("get", f"/api/sessions/{sid}/memory"), ("get", f"/api/sessions/{sid}/summary"),
                 ("get", f"/api/sessions/{sid}/handoff"), ("delete", f"/api/sessions/{sid}")]:
        assert getattr(c, m)(p, headers=bob).status_code == 404, (m, p)
    assert c.post(f"/api/sessions/{sid}/agent/turn", json={"text": "hi"}, headers=bob).status_code == 404
    assert c.get("/api/sessions", headers=bob).json()["sessions"] == [] and c.get(f"/api/sessions/{sid}", headers=alice).status_code == 200


def test_full_demo_flow_over_http_and_labels():
    _, c = make()
    h = hdr()
    sid = c.post("/api/sessions", json={}, headers=h).json()["id"]
    steps = [("My internet is down", [], False), ("beginner, here", [JPG], False), ("did it", [JPG], True), ("restarted", [JPG], True), ("cable in", [JPG], True)]
    for text, frames, done in steps:
        r = c.post(f"/api/sessions/{sid}/agent/turn", json={"text": text, "frames": frames, "reported_step_done": done}, headers=h)
        assert r.status_code == 200
        body = r.json()
        assert body["simulated"] and body["mode"] == "demo" and body["response"]["assistant_message"].startswith("[Simulated demo]")
        assert body["visually_verified"] is False
    assert body["workflow_state"] == "escalation_required"
    assert c.post(f"/api/sessions/{sid}/complete", json={}, headers=h).json()["status"].startswith("Escalated")
    assert len(c.get(f"/api/sessions/{sid}/memory", headers=h).json()["messages"]) == 10
    assert c.get("/api/sessions", headers=h).json()["sessions"][0]["final_status"] == "escalated"
    assert c.post(f"/api/sessions/{sid}/handoff/export", json={"consent_to_share": False}, headers=h).status_code == 403
    ok = c.post(f"/api/sessions/{sid}/handoff/export", json={"consent_to_share": True, "format": "md"}, headers=h)
    assert ok.status_code == 200 and "attachment" in ok.headers["content-disposition"] and "has been contacted or booked" in ok.text
    assert c.get("/api/me/export", headers=h).json()["sessions"] and c.delete("/api/me/data", headers=h).json()["deleted_sessions"] == 1


def test_unsafe_situation_stops_over_http():
    _, c = make()
    h = hdr(); sid = c.post("/api/sessions", json={}, headers=h).json()["id"]
    r = c.post(f"/api/sessions/{sid}/agent/turn", json={"text": "I can smell gas near the stove"}, headers=h).json()
    assert r["workflow_state"] == "escalation_required" and r["response"]["safety_status"] == "stop" and r["response"]["current_step"] is None


def test_input_validation_and_upload_limits():
    _, c = make()
    h = hdr(); sid = c.post("/api/sessions", json={}, headers=h).json()["id"]
    turn = f"/api/sessions/{sid}/agent/turn"
    assert c.post(turn, json={"text": ""}, headers=h).status_code == 422
    assert c.post(turn, json={"text": "x" * 2001}, headers=h).status_code == 422
    assert c.post(turn, json={"text": "hi", "frames": [JPG] * 4}, headers=h).status_code == 422
    assert c.post(turn, json={"text": "hi", "frames": [base64.b64encode(b"GIF89a....").decode()]}, headers=h).status_code == 422
    assert c.post("/api/sessions", json={"title": "x" * 500}, headers=h).status_code == 422
    assert c.post("/api/transcribe", files={"audio": ("a.wav", b"not audio", "audio/wav")}, headers=h).status_code == 422
    assert c.post("/api/transcribe", files={"audio": ("a.wav", wav(1.0, 44100), "audio/wav")}, headers=h).status_code == 422
    assert c.post("/api/transcribe", files={"audio": ("a.wav", wav(1.0), "audio/wav")}, headers=h).status_code == 503      # demo mode: no STT, honest error
    assert c.post(turn, content=b"x" * (9 * 1024 * 1024), headers={**h, "Content-Type": "application/json"}).status_code == 413


def test_cors_exact_origin_only():
    _, c = make()
    ok = c.options("/api/sessions", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
    assert ok.headers.get("access-control-allow-origin") == ORIGIN
    bad = c.options("/api/sessions", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
    assert "access-control-allow-credentials" not in ok.headers


def test_rate_limit_and_daily_quota():
    _, c = make({"EXPENSIVE_LIMIT_PER_MIN": "2"})
    h = hdr(); sid = c.post("/api/sessions", json={}, headers=h).json()["id"]
    codes = [c.post(f"/api/sessions/{sid}/agent/turn", json={"text": "hello"}, headers=h).status_code for _ in range(4)]
    assert codes[:2] == [200, 200] and 429 in codes
    _, c = make({"MAX_TURNS_PER_DAY": "1"})
    h = hdr(); sid = c.post("/api/sessions", json={}, headers=h).json()["id"]
    assert c.post(f"/api/sessions/{sid}/agent/turn", json={"text": "a"}, headers=h).status_code == 200
    r = c.post(f"/api/sessions/{sid}/agent/turn", json={"text": "b"}, headers=h)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "daily_limit"


class Failing:
    def __init__(self, err): self.err = err
    async def reason(self, **kw): raise self.err
    async def analyze(self, *a, **k): raise self.err
    async def transcribe(self, *a, **k): raise self.err


@pytest.mark.parametrize("err,status,code", [
    (ProviderError("Key rejected", code="auth_failed", status=401), 502, "auth_failed"),               # invalid API key
    (ProviderError("Could not reach", code="network_error", retryable=True), 502, "network_error"),     # network interruption
    (ProviderError("Timed out", code="timeout", retryable=True), 504, "timeout"),                       # Meta API unavailable
    (ProviderError("Down", code="upstream_error", status=503, retryable=True), 503, "upstream_error"),
    (ProviderError("Busy", code="rate_limited", status=429, retryable=True, retry_after=7), 429, "rate_limited")])
def test_ai_failures_are_reported_honestly_not_faked(err, status, code):
    from app.ai.factory import Providers
    from app.ai.demo_provider import DemoTranscriber, DemoVision
    p = Providers(DemoTranscriber(), DemoVision("router"), Failing(err), "real")
    _, c = make(providers=p)
    h = hdr(); sid = c.post("/api/sessions", json={}, headers=h).json()["id"]
    r = c.post(f"/api/sessions/{sid}/agent/turn", json={"text": "my router is down"}, headers=h)
    assert r.status_code == status and r.json()["detail"]["code"] == code and "assistant_message" not in r.text
    assert len(c.get(f"/api/sessions/{sid}/memory", headers=h).json()["messages"]) == 1       # the user's message is kept, no fake reply stored


def test_database_unavailable_returns_503_and_health_degrades():
    from app.storage import StoreUnavailable
    app, c = make()
    def boom(*a, **k): raise StoreUnavailable("down")
    app.state.memory_store.ping = boom
    app.state.memory_store.list_sessions = boom
    r = c.get("/api/sessions", headers=hdr())
    assert r.status_code == 503 and r.json()["detail"]["code"] == "database_unavailable" and r.json()["detail"]["retryable"]
    assert c.get("/api/health").status_code == 503 and c.get("/api/health/live").status_code == 200


def test_unexpected_error_does_not_leak_internals():
    app, c = make()
    app.state.memory_store.list_sessions = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret-connection-string://user:pw@host"))
    r = c.get("/api/sessions", headers=hdr())
    assert r.status_code == 500 and "secret-connection-string" not in r.text and "traceback" not in r.text.lower()


def test_security_headers_and_no_docs_in_prod():
    _, c = make()
    h = c.get("/api/health/live").headers
    assert h["x-content-type-options"] == "nosniff" and h["cache-control"] == "no-store" and h["x-frame-options"] == "DENY" and h["x-request-id"]
    prod = {"ENV": "production", "SUPABASE_URL": "https://x.supabase.co", "SUPABASE_ANON_KEY": "a", "SUPABASE_SERVICE_ROLE_KEY": "svc", "STORAGE_BACKEND": "supabase"}
    _, p = make(prod)
    assert p.get("/docs").status_code == 404 and p.get("/openapi.json").status_code == 404


def test_app_refuses_to_start_unsafely_in_production():
    with pytest.raises(RuntimeError):
        create_app(load_settings({"ENV": "production", "STORAGE_BACKEND": "memory", "ALLOWED_ORIGINS": "*"}))

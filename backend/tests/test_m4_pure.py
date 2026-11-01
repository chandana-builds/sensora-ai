"""Milestone 4 tests (stdlib only): production config guards, guest tokens, Supabase token verification,
rate limits, log redaction, storage (SQLite AND the PostgREST adapter against a fake), isolation, quotas, privacy."""
import asyncio
import logging
import socket

import pytest

from app.config import load_settings, validate, warnings
from app.security import (AuthService, AuthUnavailable, DailyQuota, RateLimiter, RedactingFilter, SupabaseVerifier,
                          issue_anon_token, redact, verify_anon_token)
from app.storage import DocMemoryStore, PostgRESTBackend, QuotaExceeded, SQLiteBackend, StoreError, StoreUnavailable
from tests.fakes import FakeSupabase

SECRET = "s" * 40
PROD = {"ENV": "production", "ALLOWED_ORIGINS": "https://sensora.vercel.app", "SUPABASE_URL": "https://x.supabase.co",
        "SUPABASE_ANON_KEY": "anon", "SUPABASE_SERVICE_ROLE_KEY": "svc", "APP_SECRET": SECRET, "MODEL_API_KEY": "k"}


# ---------- config: fail closed ----------
def test_valid_production_config_passes():
    assert validate(load_settings(PROD)) == []


@pytest.mark.parametrize("patch,needle", [
    ({"ALLOWED_ORIGINS": "*"}, "wildcard"), ({"ALLOWED_ORIGINS": ""}, "ALLOWED_ORIGINS"), ({"ALLOWED_ORIGINS": "http://evil.example"}, "https"),
    ({"STORAGE_BACKEND": "memory"}, "memory"), ({"SUPABASE_SERVICE_ROLE_KEY": ""}, "SUPABASE_SERVICE_ROLE_KEY"),
    ({"ALLOW_ANONYMOUS_DEMO": "true", "APP_SECRET": "short"}, "APP_SECRET"), ({"AI_MODE": "real", "MODEL_API_KEY": ""}, "MODEL_API_KEY"),
    ({"SUPABASE_URL": "", "SUPABASE_ANON_KEY": ""}, "authentication")])
def test_unsafe_production_config_is_rejected(patch, needle):
    errs = validate(load_settings({**PROD, **patch}))
    assert errs and any(needle in e for e in errs), errs


def test_dev_defaults_and_warnings():
    s = load_settings({"APP_SECRET": SECRET})
    assert s.storage_backend == "sqlite" and s.allow_anonymous_demo and "http://localhost:5173" in s.allowed_origins and validate(s) == []
    assert any("DEMO" in w for w in warnings(s))
    assert any("ephemeral" in w for w in warnings(load_settings({**PROD, "STORAGE_BACKEND": "sqlite"})))
    assert not load_settings(PROD).allow_anonymous_demo          # guests are off by default in production


# ---------- guest tokens ----------
def test_anon_tokens_unique_verifiable_unforgeable():
    t1, t2 = issue_anon_token(SECRET), issue_anon_token(SECRET)
    u1 = verify_anon_token(SECRET, t1)
    assert t1 != t2 and u1.startswith("anon:") and u1 != verify_anon_token(SECRET, t2)
    assert verify_anon_token("other-secret-" + "x" * 30, t1) is None
    a, b, sig = t1.split(".")
    assert verify_anon_token(SECRET, f"anon.{'A' * 22}.{sig}") is None        # swapping the id breaks the signature
    for bad in ("", "anon", "anon.x.y", "Bearer x", t1 + "x", "user." + b + "." + sig):
        assert verify_anon_token(SECRET, bad) is None


# ---------- Supabase token verification ----------
def test_supabase_verifier_valid_invalid_cached_and_outage():
    f = FakeSupabase()
    try:
        now = [0.0]
        v = SupabaseVerifier(f.url, "anon-key", ttl=60, clock=lambda: now[0])
        assert v.verify("good-token") == "user:11111111-aaaa"
        n = len(f.requests)
        assert v.verify("good-token") == "user:11111111-aaaa" and len(f.requests) == n      # cached
        now[0] = 61
        v.verify("good-token")
        assert len(f.requests) == n + 1                                                       # cache expired
        assert v.verify("forged-token") is None
        f.fail_status = 500
        with pytest.raises(AuthUnavailable):
            SupabaseVerifier(f.url, "anon-key").verify("another-token")
    finally:
        f.close()
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    with pytest.raises(AuthUnavailable):
        SupabaseVerifier(f"http://127.0.0.1:{port}", "k", timeout=1).verify("t")


def test_auth_service_routing():
    f = FakeSupabase()
    try:
        svc = AuthService(allow_anonymous=True, secret=SECRET, verifier=SupabaseVerifier(f.url, "anon-key"))
        assert asyncio.run(svc.authenticate(issue_anon_token(SECRET))).startswith("anon:")
        assert asyncio.run(svc.authenticate("good-token")).startswith("user:")
        assert asyncio.run(svc.authenticate("nope")) is None
        off = AuthService(allow_anonymous=False, secret=SECRET, verifier=None)
        assert asyncio.run(off.authenticate(issue_anon_token(SECRET))) is None and asyncio.run(off.authenticate("good-token")) is None
    finally:
        f.close()


# ---------- limits ----------
def test_rate_limiter_and_daily_quota():
    t = [0.0]
    rl = RateLimiter(3, 60, clock=lambda: t[0])
    assert [rl.allow("a")[0] for _ in range(4)] == [True, True, True, False] and rl.allow("b")[0]
    ok, retry = rl.allow("a")
    assert not ok and retry >= 1
    t[0] = 61
    assert rl.allow("a")[0]
    day = ["d1"]
    q = DailyQuota(2, today=lambda: day[0])
    assert [q.allow("u")[0] for _ in range(3)] == [True, True, False]
    day[0] = "d2"
    assert q.allow("u")[0]


# ---------- log redaction ----------
def test_redaction():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk"
    anon = issue_anon_token(SECRET)
    for raw in (f"Authorization: Bearer {jwt}", f"token={jwt}", f"guest {anon}", "MODEL_API_KEY=sk-live-12345678", "api_key: abcdef123456",
                "service_role_key = svc-secret-value", "x" * 300):
        out = redact(raw)
        assert jwt not in out and anon not in out and "sk-live-12345678" not in out and "abcdef123456" not in out and "svc-secret-value" not in out and "x" * 200 not in out, out
    assert "hunter2hunter2" not in redact("config value hunter2hunter2", ["hunter2hunter2"])
    assert redact("GET /api/health -> 200 12ms") == "GET /api/health -> 200 12ms"


def test_redacting_filter_cleans_records_and_tracebacks():
    f = RedactingFilter(["topsecretvalue"])
    try:
        raise RuntimeError("boom topsecretvalue")
    except RuntimeError:
        import sys
        rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "key=%s", ("topsecretvalue",), sys.exc_info())
    f.filter(rec)
    assert "topsecretvalue" not in rec.msg and "topsecretvalue" not in (rec.exc_text or "") and rec.exc_info is None


# ---------- storage suite: runs against SQLite and the PostgREST adapter ----------
A, B = "user:alice", "anon:bobbobbobbobbobbobbob1"


def store_suite(mk):
    st: DocMemoryStore = mk()
    s = st.new_session(A, title="Router down", problem="no internet", user_level="beginner", is_admin=True, workflow_state="resolved")
    assert s["workflow_state"] == "problem_reported" and s["user_level"] == "beginner" and "is_admin" not in s    # client cannot set internals
    sid = s["id"]
    # isolation: another user cannot see, modify, delete or add to it
    assert st.get_session(B, sid) is None and st.list_sessions(B) == [] and st.delete_session(B, sid) == 0
    with pytest.raises(KeyError):
        st.update_session(B, sid, final_status="x")
    assert st.list_messages(B, sid) == [] and st.get_session(A, sid)["id"] == sid
    # messages: order, limit, metadata
    for i in range(5):
        st.add_message(A, sid, role="user" if i % 2 == 0 else "assistant", content=f"m{i}", metadata={"i": i})
    assert [m["content"] for m in st.list_messages(A, sid, 3)] == ["m2", "m3", "m4"] and st.list_messages(A, sid)[0]["metadata"] == {"i": 0}
    # steps merge-update
    stp = st.add_step(A, sid, title="Restart", status="awaiting_user", user_reported_complete=False, visually_verified=False)
    st.update_step(A, sid, stp["id"], user_reported_complete=True)
    got = st.list_steps(A, sid)[0]
    assert got["user_reported_complete"] is True and got["visually_verified"] is False and got["title"] == "Restart"
    with pytest.raises(KeyError):
        st.update_step(B, sid, stp["id"], visually_verified=True)
    # observations dedupe
    st.add_observations(A, sid, ["amber light", "amber light", "router"], True)
    assert [o["text"] for o in st.list_observations(A, sid)] == ["amber light", "router"] and st.list_observations(A, sid)[0]["simulated"] is True
    # evidence needs consent, is capped, listed without data, erased on delete, and purged after expiry
    assert st.save_evidence(A, sid, b"\xff\xd8\xff", "f", 30) is None
    st.update_session(A, sid, evidence_consent=True)
    metas = [st.save_evidence(A, sid, b"\xff\xd8\xff\x00", "frame", 30) for _ in range(6)]
    assert [m is not None for m in metas] == [True] * 5 + [False]
    ev = st.list_evidence(A, sid)
    assert len(ev) == 5 and "data" not in ev[0] and st.list_evidence(B, sid) == []
    st.save_evidence  # noqa
    assert st.purge_expired_evidence() == 0
    assert st.delete_evidence(A, sid) == 5 and st.list_evidence(A, sid) == []
    st.save_evidence(A, sid, b"\xff\xd8\xff\x00", "old", -1)
    assert st.purge_expired_evidence() == 1
    # preferences only with consent
    assert st.set_experience_level(A, "beginner", False)["user_level"] is None
    assert st.set_experience_level(A, "experienced", True) == {"user_level": "experienced", "remember_level": True}
    assert st.get_preferences(B)["user_level"] is None
    assert st.set_experience_level(A, "experienced", False)["user_level"] is None
    # export + cascade delete + delete-all
    st.update_session(A, sid, final_status="escalated")
    ex = st.export_all(A)
    assert len(ex["sessions"]) == 1 and len(ex["sessions"][0]["messages"]) == 5 and st.export_all(B)["sessions"] == []
    assert st.delete_session(A, sid) == 1
    assert st.list_messages(A, sid) == [] and st.list_steps(A, sid) == [] and st.list_observations(A, sid) == []
    a1, a2 = st.new_session(A), st.new_session(A)
    st.new_session(B)
    assert [x["id"] for x in st.list_sessions(A)] == [a2["id"], a1["id"]]       # newest first
    assert st.delete_all(A) == 2 and st.list_sessions(A) == [] and len(st.list_sessions(B)) == 1
    st.ping()
    # quotas
    small = DocMemoryStore(st.b, max_sessions=2, max_messages=3)
    small.new_session("q"); q2 = small.new_session("q")
    with pytest.raises(QuotaExceeded):
        small.new_session("q")
    for _ in range(3):
        small.add_message("q", q2["id"], role="user", content="x")
    with pytest.raises(QuotaExceeded):
        small.add_message("q", q2["id"], role="user", content="x")


def test_store_suite_sqlite():
    store_suite(lambda: DocMemoryStore(SQLiteBackend(":memory:")))


def test_store_suite_postgrest_adapter_against_fake():
    f = FakeSupabase()
    try:
        store_suite(lambda: DocMemoryStore(PostgRESTBackend(f.url, "svc-key")))
        methods = {m for m, _, _ in f.requests}
        assert {"GET", "POST", "PATCH", "DELETE"} <= methods
        assert all({k.lower(): v for k, v in h.items()}.get("apikey") == "svc-key" for _, p, h in f.requests if p.startswith("/rest/v1"))
        blob = [r for r in f.tables["sensora_evidence"]]
        assert all(isinstance(r["data"], str) and r["data"].startswith("\\x") for r in blob)      # bytea hex encoding
    finally:
        f.close()


def test_postgrest_failures_map_to_store_errors():
    f = FakeSupabase()
    try:
        with pytest.raises(StoreUnavailable):
            DocMemoryStore(PostgRESTBackend(f.url, "WRONG-KEY")).list_sessions(A)             # rejected credentials
        f.fail_status = 503
        with pytest.raises(StoreUnavailable):
            DocMemoryStore(PostgRESTBackend(f.url, "svc-key")).ping()
        f.fail_status = 400
        with pytest.raises(StoreError):
            DocMemoryStore(PostgRESTBackend(f.url, "svc-key")).ping()
    finally:
        f.close()
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    with pytest.raises(StoreUnavailable):                                                       # network interruption / DB down
        DocMemoryStore(PostgRESTBackend(f"http://127.0.0.1:{port}", "k", timeout=1)).list_sessions(A)


def test_sqlite_persists_across_restart(tmp_path=None):
    import os, tempfile
    path = os.path.join(tempfile.mkdtemp(), "t.db")
    s1 = DocMemoryStore(SQLiteBackend(path))
    sid = s1.new_session(A, title="persist me")["id"]
    s1.add_message(A, sid, role="user", content="hello")
    s2 = DocMemoryStore(SQLiteBackend(path))            # new process, same file
    assert s2.get_session(A, sid)["title"] == "persist me" and s2.list_messages(A, sid)[0]["content"] == "hello"


def test_store_with_agent_orchestrator_end_to_end_persists():
    """The real agent orchestrator on the real (SQLite) store: demo scenario survives a 'restart'."""
    import base64, os, tempfile
    from types import SimpleNamespace as NS
    from app.ai.config import load_ai_settings
    from app.ai.demo_provider_v3 import build_providers_v3
    from app.services.agent_orchestrator import AgentOrchestrator
    path = os.path.join(tempfile.mkdtemp(), "e2e.db")
    jpg = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 64).decode()
    st = DocMemoryStore(SQLiteBackend(path))
    sid = st.new_session(A)["id"]
    p = build_providers_v3(load_ai_settings({"AI_MODE": "demo", "DEMO_SCENARIO": "induction"}))
    o = AgentOrchestrator(st, p)
    for text, frames, done in [("My induction stove is not heating", [], False), ("beginner, here it is", [jpg], False), ("magnet test done", [jpg], True), ("tried unlock", [jpg], True), ("still not", [jpg], True)]:
        out = asyncio.run(o.handle_turn(A, sid, NS(text=text, frames=frames, input_mode="text", user_level=None, reported_step_done=done)))
    assert out["workflow_state"] == "escalation_required" and out["simulated"]
    o.complete(A, sid, None)
    st2 = DocMemoryStore(SQLiteBackend(path))
    o2 = AgentOrchestrator(st2, p)
    s = st2.get_session(A, sid)
    assert s["workflow_state"] == "session_completed" and s["final_status"] == "escalated" and s["summary"]["simulated"]
    assert len(st2.list_messages(A, sid, 100)) == 10 and all(not x["visually_verified"] for x in st2.list_steps(A, sid))
    h = o2.handoff(A, sid, "local_technician", False)
    assert "Induction cooktop" in h["title"] and h["possible_causes"]
    with pytest.raises(Exception):
        asyncio.run(AgentOrchestrator(st2, p).handle_turn(B, sid, NS(text="hi", frames=[], input_mode="text", user_level=None, reported_step_done=False)))

import pytest
from starlette.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage import DocMemoryStore, SQLiteBackend


def test_local_register_and_login_flow():
    # Setup test app with SQLite backend and no Supabase credentials
    settings = Settings(
        env="development",
        allowed_origins=("http://localhost:5173",),
        allowed_origin_regex=None,
        allow_anonymous_demo=True,
        app_secret="test-secret-long-enough-32-chars-ok!",
        supabase_url=None,
        supabase_anon_key=None,
        supabase_service_key=None,
        storage_backend="sqlite",
        sqlite_path=":memory:",
        rate_limit_per_min=120,
        expensive_limit_per_min=20,
        max_turns_per_day=100,
        max_body_bytes=1024 * 1024,
        max_sessions_per_user=50,
        max_messages_per_session=100,
        evidence_retention_days=7,
        ai_mode="demo",
        model_api_key=None,
    )
    b = SQLiteBackend(":memory:")
    store = DocMemoryStore(b)
    app = create_app(settings, store=store)
    client = TestClient(app)

    # 1. Reject short password
    r = client.post("/api/auth/register", json={"email": "test@example.com", "password": "short"})
    assert r.status_code == 400

    # 2. Register valid user
    r = client.post(
        "/api/auth/register",
        json={"email": "alex@example.com", "password": "SecurePassword123!", "display_name": "Alex T"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["email"] == "alex@example.com"
    assert data["display_name"] == "Alex T"
    assert "token" in data

    token = data["token"]

    # 3. Duplicate email returns 409 Conflict
    r = client.post(
        "/api/auth/register",
        json={"email": "alex@example.com", "password": "SecurePassword123!"},
    )
    assert r.status_code == 409

    # 4. Login with correct password
    r = client.post(
        "/api/auth/login",
        json={"email": "alex@example.com", "password": "SecurePassword123!"},
    )
    assert r.status_code == 200
    login_data = r.json()
    assert "token" in login_data
    assert login_data["email"] == "alex@example.com"

    # 5. Login with incorrect password
    r = client.post(
        "/api/auth/login",
        json={"email": "alex@example.com", "password": "WrongPassword!"},
    )
    assert r.status_code == 401

    # 6. Use the token to access protected endpoints
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["kind"] == "account"

    # 7. Create a session using this user token
    r = client.post(
        "/api/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"device_name": "Wi-Fi Router"},
    )
    assert r.status_code == 201
    sid = r.json()["id"]

    # 8. Retrieve the session list
    r = client.get("/api/sessions", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    sessions = r.json()["sessions"]
    assert len(sessions) >= 1
    assert any(s["id"] == sid for s in sessions)

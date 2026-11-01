from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..deps import current_user
from ..security import issue_anon_token, issue_user_token

router = APIRouter(tags=["auth"])
log = logging.getLogger("sensora.auth")


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


@router.post("/auth/guest")
async def guest(request: Request):
    """Issue a signed guest token (public demo only). One token = one private workspace; it cannot be used to read anyone else's."""
    s = request.app.state.settings
    if not s.allow_anonymous_demo:
        raise HTTPException(403, "Guest access is disabled. Please sign in.")
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "unknown"))
    ok, retry = request.app.state.guest_limiter.allow(ip)
    if not ok:
        raise HTTPException(429, "Too many guest sessions from this network. Try again later.", headers={"Retry-After": str(int(retry))})
    return {
        "token": issue_anon_token(s.app_secret),
        "kind": "guest",
        "note": "Guest data lives only under this browser's token. Clearing browser data loses access to it.",
    }


@router.post("/auth/register")
async def register(req: RegisterRequest, request: Request):
    """Register a new account.
    If Supabase is configured, uses the Admin API with email_confirm: true so user is created
    without sending verification emails or hitting the email rate limit.
    Falls back gracefully to local SQLite database if Supabase is unavailable.
    """
    s = request.app.state.settings
    clean_email = req.email.strip().lower()
    clean_display = (req.display_name or "").strip() or clean_email.split("@")[0]

    if len(req.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters long.")

    # 1. Primary: Auto-confirmed Supabase Admin Registration (Zero rate limit!)
    if s.supabase_url and s.supabase_service_key:
        supa_url = f"{s.supabase_url}/auth/v1/admin/users"
        headers = {
            "apikey": s.supabase_service_key,
            "Authorization": f"Bearer {s.supabase_service_key}",
            "Content-Type": "application/json",
        }
        body = json.dumps({
            "email": clean_email,
            "password": req.password,
            "email_confirm": True,
            "user_metadata": {"display_name": clean_display},
        }).encode()
        supa_req = urllib.request.Request(supa_url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(supa_req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode())
                supa_id = data.get("id")
                log.info("Registered user %s via Supabase Admin API with auto-confirmation", clean_email)
                # Mirror in local SQLite so local fallback login works seamlessly
                mem_store = getattr(request.app.state, "memory_store", None)
                backend = getattr(mem_store, "b", None)
                if backend and hasattr(backend, "create_user"):
                    try:
                        salt = s.app_secret or "sensora-app-secret-default"
                        pw_hash = hashlib.sha256(f"{clean_email}:{req.password}:{salt}".encode()).hexdigest()
                        backend.create_user(supa_id, clean_email, pw_hash, clean_display)
                    except Exception:
                        pass
                return {
                    "ok": True,
                    "provider": "supabase",
                    "user_id": supa_id,
                    "email": clean_email,
                    "display_name": clean_display,
                    "auto_confirmed": True,
                    "message": "Account created and auto-confirmed in Supabase.",
                }
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            log.warning("Supabase Admin registration returned HTTP %d: %s", e.code, raw)
            try:
                err_json = json.loads(raw)
            except Exception:
                err_json = {}
            msg = err_json.get("msg") or err_json.get("message") or ""
            if e.code == 422 or "already" in msg.lower() or "unique" in msg.lower():
                raise HTTPException(409, "An account with this email address already exists. Please sign in.")
        except Exception as exc:
            log.warning("Supabase Admin registration error: %s. Falling back to local database.", exc)

    # 2. Secondary Fallback: Local Database (SQLite)
    mem_store = getattr(request.app.state, "memory_store", None)
    backend = getattr(mem_store, "b", None)
    if backend and hasattr(backend, "get_user_by_email"):
        existing = backend.get_user_by_email(clean_email)
        if existing:
            raise HTTPException(409, "An account with this email address already exists. Please sign in.")
        uid = _b64u(os.urandom(16))
        salt = s.app_secret or "sensora-app-secret-default"
        pw_hash = hashlib.sha256(f"{clean_email}:{req.password}:{salt}".encode()).hexdigest()
        backend.create_user(uid, clean_email, pw_hash, clean_display)
        token = issue_user_token(s.app_secret, uid) if s.app_secret else f"user:{uid}"
        log.info("Registered user %s via local SQLite storage", clean_email)
        return {
            "ok": True,
            "provider": "sqlite",
            "token": token,
            "user_id": uid,
            "email": clean_email,
            "display_name": clean_display,
            "message": "Account created in local SQLite database.",
        }

    raise HTTPException(500, "Unable to register account: no storage backend available.")


@router.post("/auth/login")
async def local_login(req: LoginRequest, request: Request):
    """Authenticate against local SQLite database if user is stored locally."""
    s = request.app.state.settings
    clean_email = req.email.strip().lower()
    mem_store = getattr(request.app.state, "memory_store", None)
    backend = getattr(mem_store, "b", None)
    if backend and hasattr(backend, "get_user_by_email"):
        user = backend.get_user_by_email(clean_email)
        if user:
            salt = s.app_secret or "sensora-app-secret-default"
            pw_hash = hashlib.sha256(f"{clean_email}:{req.password}:{salt}".encode()).hexdigest()
            if hmac.compare_digest(user["password_hash"], pw_hash):
                token = issue_user_token(s.app_secret, user["id"]) if s.app_secret else f"user:{user['id']}"
                return {
                    "token": token,
                    "kind": "account",
                    "user_id": user["id"],
                    "email": user["email"],
                    "displayName": user["display_name"],
                }
    raise HTTPException(401, "Invalid email address or password.")


@router.get("/auth/me")
async def me(uid: str = Depends(current_user)):
    return {"user_id": uid, "kind": "guest" if uid.startswith("anon:") else "account"}

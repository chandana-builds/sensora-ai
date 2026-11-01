"""Central, validated settings. In production the app REFUSES to start on unsafe configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

VERSION = "1.0.0-hackathon"


def _int(e: Mapping[str, str], k: str, d: int) -> int:
    try:
        return int(e.get(k, d))
    except ValueError:
        return d


@dataclass(frozen=True)
class Settings:
    env: str
    allowed_origins: tuple[str, ...]
    allowed_origin_regex: str | None
    allow_anonymous_demo: bool
    app_secret: str | None
    supabase_url: str | None
    supabase_anon_key: str | None
    supabase_service_key: str | None
    storage_backend: str            # supabase | sqlite | memory
    sqlite_path: str
    rate_limit_per_min: int
    expensive_limit_per_min: int
    max_turns_per_day: int
    max_body_bytes: int
    max_sessions_per_user: int
    max_messages_per_session: int
    evidence_retention_days: int
    ai_mode: str
    model_api_key: str | None
    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    version: str = VERSION

    @property
    def is_prod(self) -> bool:
        return self.env == "production"

    @property
    def supabase_auth_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)

    def secrets(self) -> list[str]:
        return [x for x in (self.app_secret, self.supabase_service_key, self.supabase_anon_key, self.model_api_key, self.gemini_api_key, self.groq_api_key) if x]


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    if env is None:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
    e = os.environ if env is None else env
    prod = e.get("ENV", "development").lower() == "production"
    origins = tuple(o.strip().rstrip("/") for o in e.get("ALLOWED_ORIGINS", "" if prod else "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip())
    return Settings(
        env="production" if prod else "development", allowed_origins=origins,
        allowed_origin_regex=e.get("ALLOWED_ORIGIN_REGEX") or (None if prod else r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"),
        allow_anonymous_demo=e.get("ALLOW_ANONYMOUS_DEMO", "false" if prod else "true").lower() == "true",
        app_secret=e.get("APP_SECRET") or None,
        supabase_url=(e.get("SUPABASE_URL") or "").rstrip("/") or None,
        supabase_anon_key=e.get("SUPABASE_ANON_KEY") or None,
        supabase_service_key=e.get("SUPABASE_SERVICE_ROLE_KEY") or None,
        storage_backend=e.get("STORAGE_BACKEND", "supabase" if prod else "sqlite").lower(),
        sqlite_path=e.get("SQLITE_PATH", "sensora_dev.db"),
        rate_limit_per_min=_int(e, "RATE_LIMIT_PER_MIN", 120), expensive_limit_per_min=_int(e, "EXPENSIVE_LIMIT_PER_MIN", 20),
        max_turns_per_day=_int(e, "MAX_TURNS_PER_DAY", 100), max_body_bytes=_int(e, "MAX_BODY_BYTES", 8 * 1024 * 1024),
        max_sessions_per_user=_int(e, "MAX_SESSIONS_PER_USER", 200), max_messages_per_session=_int(e, "MAX_MESSAGES_PER_SESSION", 500),
        evidence_retention_days=_int(e, "EVIDENCE_RETENTION_DAYS", 30),
        ai_mode=e.get("AI_MODE", "auto").lower(), model_api_key=e.get("MODEL_API_KEY") or None,
        gemini_api_key=e.get("GEMINI_API_KEY") or None,
        groq_api_key=e.get("GROQ_API_KEY") or None)


def validate(s: Settings) -> list[str]:
    """Hard errors. In production the app must not start if any are returned."""
    err: list[str] = []
    if s.storage_backend not in ("supabase", "sqlite", "memory"):
        err.append("STORAGE_BACKEND must be supabase, sqlite or memory")
    if s.storage_backend == "supabase" and not (s.supabase_url and s.supabase_service_key):
        err.append("STORAGE_BACKEND=supabase needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
    if s.allow_anonymous_demo and (not s.app_secret or len(s.app_secret) < 32):
        err.append("ALLOW_ANONYMOUS_DEMO needs APP_SECRET of at least 32 characters (used to sign guest tokens)")
    if s.ai_mode not in ("auto", "real", "demo"):
        err.append("AI_MODE must be auto, real or demo")
    if s.ai_mode == "real" and not (s.model_api_key or s.gemini_api_key or s.groq_api_key):
        err.append("AI_MODE=real needs at least one provider key (MODEL_API_KEY, GEMINI_API_KEY, or GROQ_API_KEY)")
    if s.is_prod:
        if s.storage_backend == "memory":
            err.append("STORAGE_BACKEND=memory is not allowed in production")
        if not s.allowed_origins and not s.allowed_origin_regex:
            err.append("ALLOWED_ORIGINS must list the exact frontend origin(s) in production")
        for o in s.allowed_origins:
            if o == "*" or not o.startswith("https://"):
                err.append(f"ALLOWED_ORIGINS entry '{o}' must be an exact https:// origin (no wildcard)")
        if not (s.supabase_auth_enabled or s.allow_anonymous_demo):
            err.append("Production needs authentication: set SUPABASE_URL + SUPABASE_ANON_KEY, or ALLOW_ANONYMOUS_DEMO=true for a public demo")
    return err


def warnings(s: Settings) -> list[str]:
    w: list[str] = []
    if s.is_prod and s.storage_backend == "sqlite":
        w.append("SQLite on a free Render instance is ephemeral: data is lost on redeploy/restart. Use supabase for persistence.")
    if s.ai_mode == "auto" and not s.model_api_key:
        w.append("No MODEL_API_KEY: the app will run in clearly labelled DEMO mode (simulated).")
    if s.allow_anonymous_demo:
        w.append("Guest (anonymous) access is enabled: fine for a demo, but guests are not verified identities.")
    if s.allowed_origin_regex:
        w.append("ALLOWED_ORIGIN_REGEX is set: make sure it cannot match origins you don't control.")
    return w

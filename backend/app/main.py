"""Sensora AI API entrypoint:  uvicorn app.main:app"""
from __future__ import annotations
# Trigger server reload

import logging
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .ai.base import ProviderError
from .ai.config import load_ai_settings
from .config import Settings, load_settings, validate, warnings
from .middleware import BodyLimitMiddleware, GuardMiddleware
from .routes import agent, auth, live, sessions
from .security import AuthService, DailyQuota, RateLimiter, RedactingFilter, SupabaseVerifier
from .storage import QuotaExceeded, StoreError, StoreUnavailable, build_store

log = logging.getLogger("sensora")


def _logging(s: Settings) -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for h in logging.getLogger().handlers:
        h.addFilter(RedactingFilter(s.secrets()))


def create_app(settings: Settings | None = None, *, store=None, providers_v3=None) -> FastAPI:
    s = settings or load_settings()
    _logging(s)
    errors = validate(s)
    if errors:
        raise RuntimeError("Refusing to start with unsafe/incomplete configuration:\n - " + "\n - ".join(errors))
    for w in warnings(s):
        log.warning(w)

    app = FastAPI(title="Sensora AI API", version=s.version, docs_url=None if s.is_prod else "/docs", redoc_url=None,
                  openapi_url=None if s.is_prod else "/openapi.json")
    st = app.state
    st.settings, st.memory_store = s, store or build_store(s)
    st.daily, st.guest_limiter = DailyQuota(s.max_turns_per_day), RateLimiter(10, 3600.0)
    st.auth = AuthService(allow_anonymous=s.allow_anonymous_demo, secret=s.app_secret,
                          verifier=SupabaseVerifier(s.supabase_url, s.supabase_anon_key) if s.supabase_auth_enabled else None)
    if providers_v3 is not None:
        st.ai_providers_v3 = providers_v3

    # last added = outermost: CORS wraps everything so 413/429/5xx responses still carry CORS headers
    app.add_middleware(GuardMiddleware, per_min=s.rate_limit_per_min, expensive_per_min=s.expensive_limit_per_min)
    app.add_middleware(BodyLimitMiddleware, max_bytes=s.max_body_bytes)
    app.add_middleware(CORSMiddleware, allow_origins=list(s.allowed_origins), allow_origin_regex=s.allowed_origin_regex, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], allow_headers=["*"], max_age=600)

    @app.exception_handler(StoreUnavailable)
    async def _db_down(_: Request, exc: StoreUnavailable):
        log.error("database unavailable: %s", exc)
        return JSONResponse({"detail": {"code": "database_unavailable", "message": "The database is unreachable. Your data is safe; please try again shortly.", "retryable": True}}, status_code=503)

    @app.exception_handler(StoreError)
    async def _db_err(_: Request, exc: StoreError):
        log.error("database error: %s", exc)
        return JSONResponse({"detail": {"code": "database_error", "message": "The database rejected the request.", "retryable": False}}, status_code=502)

    @app.exception_handler(QuotaExceeded)
    async def _quota(_: Request, exc: QuotaExceeded):
        return JSONResponse({"detail": {"code": "quota_exceeded", "message": str(exc), "retryable": False}}, status_code=429)

    @app.exception_handler(ProviderError)
    async def _provider(_: Request, exc: ProviderError):
        h = live._http(exc)
        return JSONResponse({"detail": h.detail}, status_code=h.status_code, headers=h.headers)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s %s", request.method, request.url.path)          # redacted by the log filter
        return JSONResponse({"detail": {"code": "internal_error", "message": "Something went wrong on our side."}}, status_code=500)

    @app.get("/health/live", tags=["health"])
    @app.get("/api/health/live", tags=["health"])
    async def health_live():
        """Cheap liveness probe for Render. Does not touch the database or AI."""
        return {"status": "ok", "version": s.version}

    @app.get("/health", tags=["health"])
    @app.get("/api/health", tags=["health"])
    async def health():
        """Deep check: storage reachable, AI mode, auth mode. Never returns secrets."""
        ai = load_ai_settings({"AI_MODE": s.ai_mode, "MODEL_API_KEY": s.model_api_key or "", "GEMINI_API_KEY": s.gemini_api_key or "", "GROQ_API_KEY": s.groq_api_key or ""})
        storage_ok, storage_err = True, None
        try:
            st.memory_store.ping()
        except Exception as exc:  # noqa: BLE001
            storage_ok, storage_err = False, type(exc).__name__
        body = {"status": "ok" if storage_ok else "degraded", "version": s.version, "env": s.env,
                "ai": {"mode": ai.effective_mode, "simulated": ai.effective_mode == "demo", "models_configured": bool(ai.api_key or ai.gemini_api_key or ai.groq_api_key)},
                "storage": {"backend": s.storage_backend, "ok": storage_ok, **({"error": storage_err} if storage_err else {})},
                "auth": {"accounts": s.supabase_auth_enabled, "guest": s.allow_anonymous_demo}}
        return JSONResponse(body, status_code=200 if storage_ok else 503)

    for r in (live.router, auth.router, sessions.router, agent.router):
        app.include_router(r, prefix="/api")
    return app


app = None if "pytest" in sys.modules else create_app()

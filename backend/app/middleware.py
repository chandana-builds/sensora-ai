from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .security import RateLimiter

log = logging.getLogger("sensora.http")
_EXPENSIVE = re.compile(r"/(agent/turn|transcribe)$")


class BodyLimitMiddleware:
    """Pure ASGI: rejects oversized bodies even when Content-Length is absent (chunked uploads)."""

    def __init__(self, app, max_bytes: int) -> None:
        self.app, self.max = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        declared = dict(scope["headers"]).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > self.max:
            return await self._reject(scope, receive, send)
        seen = 0

        async def limited():
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > self.max:
                    raise _TooBig()
            return msg
        try:
            await self.app(scope, limited, send)
        except _TooBig:
            await self._reject(scope, receive, send)

    async def _reject(self, scope, receive, send):
        await JSONResponse({"detail": "Request body too large."}, status_code=413)(scope, receive, send)


class _TooBig(Exception):
    pass


class GuardMiddleware(BaseHTTPMiddleware):
    """Request id, rate limiting, security headers, and metadata-only access logs (never bodies or headers)."""

    def __init__(self, app, *, per_min: int, expensive_per_min: int) -> None:
        super().__init__(app)
        self.general, self.expensive = RateLimiter(per_min), RateLimiter(expensive_per_min)

    def _key(self, request) -> str:
        auth = request.headers.get("authorization")
        if auth:
            return "t:" + hashlib.sha256(auth.encode()).hexdigest()[:16]
        fwd = request.headers.get("x-forwarded-for", "")
        return "ip:" + (fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown"))

    async def dispatch(self, request, call_next):
        rid, t0 = uuid.uuid4().hex[:12], time.monotonic()
        path = request.url.path
        if request.method != "OPTIONS" and not path.endswith("/health/live"):
            key = self._key(request)
            for lim in ((self.expensive, key + "|x") if _EXPENSIVE.search(path) else None, (self.general, key)):
                if lim:
                    ok, retry = lim[0].allow(lim[1])
                    if not ok:
                        return JSONResponse({"detail": {"code": "rate_limited", "message": "Too many requests. Please slow down.", "retryable": True}},
                                            status_code=429, headers={"Retry-After": str(int(retry)), "X-Request-Id": rid})
        response = await call_next(request)
        response.headers.update({"X-Request-Id": rid, "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                                 "Cache-Control": "no-store", "X-Frame-Options": "DENY"})
        log.info("%s %s -> %s %.0fms rid=%s", request.method, path, response.status_code, (time.monotonic() - t0) * 1000, rid)
        return response

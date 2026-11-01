from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from .security import AuthUnavailable


async def current_user(request: Request) -> str:
    """Resolve the caller from `Authorization: Bearer <token>`. 401 = not signed in, 503 = auth provider down."""
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer ") or len(h) > 4096:
        raise HTTPException(401, "Sign in required.", headers={"WWW-Authenticate": "Bearer"})
    try:
        uid = await request.app.state.auth.authenticate(h[7:].strip())
    except AuthUnavailable:
        raise HTTPException(503, {"code": "auth_unavailable", "message": "The sign-in service is unreachable. Try again shortly.", "retryable": True})
    if not uid:
        raise HTTPException(401, "Your session is invalid or has expired. Please sign in again.", headers={"WWW-Authenticate": "Bearer"})
    request.state.user = uid
    return uid


async def user_with_quota(request: Request, cid: str = Depends(current_user)) -> str:
    """For endpoints that cost model calls: also enforces the per-user daily cap."""
    ok, retry = request.app.state.daily.allow(cid)
    if not ok:
        raise HTTPException(429, {"code": "daily_limit", "message": "Daily AI usage limit for this demo reached. Try again tomorrow.", "retryable": False},
                            headers={"Retry-After": str(int(retry))})
    return cid

"""Identifying the caller.

anonymous mode (default): the browser sends a random UUID in `X-Client-Id`.
    This separates users' data but is NOT strong authentication — anyone who
    learns a client id can read that data. Use `supabase` mode for real accounts.
supabase mode: a Supabase Auth JWT is required (`Authorization: Bearer ...`).
"""
import re
from dataclasses import dataclass

from fastapi import Depends, Request

from .config import Settings, get_settings
from .errors import AppError

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I
)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    is_anonymous: bool


def _from_jwt(token: str, settings: Settings) -> CurrentUser:
    if not settings.supabase_jwt_secret:
        raise AppError(500, "auth_misconfigured", "AUTH_MODE=supabase requires SUPABASE_JWT_SECRET.")
    import jwt  # PyJWT, imported lazily so anonymous mode has no hard dependency

    try:
        claims = jwt.decode(
            token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated"
        )
    except jwt.PyJWTError as exc:
        raise AppError(401, "invalid_token", "The access token is invalid or expired.") from exc
    sub = str(claims.get("sub", ""))
    if not _UUID_RE.match(sub):
        raise AppError(401, "invalid_token", "The access token has no valid subject.")
    return CurrentUser(id=sub.lower(), is_anonymous=False)


def get_current_user(request: Request, settings: Settings = Depends(get_settings)) -> CurrentUser:
    if settings.auth_mode == "supabase":
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise AppError(401, "not_authenticated", "Sign in to use this endpoint.")
        return _from_jwt(token.strip(), settings)

    client_id = request.headers.get("x-client-id", "").strip()
    if not _UUID_RE.match(client_id):
        raise AppError(401, "missing_client_id", "A valid X-Client-Id header (UUID) is required.")
    return CurrentUser(id=client_id.lower(), is_anonymous=True)

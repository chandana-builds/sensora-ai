"""Auth, rate limiting and log redaction. Pure stdlib so it is testable without FastAPI."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
import traceback
import urllib.error
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Callable


class AuthUnavailable(Exception):
    """The identity provider could not be reached (distinct from 'invalid token')."""


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


# ---- guest tokens: unguessable, server-signed, so one guest can never impersonate another ----
def issue_anon_token(secret: str) -> str:
    uid = _b64u(os.urandom(16))
    sig = _b64u(hmac.new(secret.encode(), f"anon.{uid}".encode(), hashlib.sha256).digest()[:24])
    return f"anon.{uid}.{sig}"


def verify_anon_token(secret: str, token: str) -> str | None:
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "anon" or not re.fullmatch(r"[A-Za-z0-9_\-]{22}", parts[1]):
        return None
    good = _b64u(hmac.new(secret.encode(), f"anon.{parts[1]}".encode(), hashlib.sha256).digest()[:24])
    return f"anon:{parts[1]}" if hmac.compare_digest(good, parts[2]) else None


def issue_user_token(secret: str, user_id: str) -> str:
    sig = _b64u(hmac.new(secret.encode(), f"act.{user_id}".encode(), hashlib.sha256).digest()[:24])
    return f"act.{user_id}.{sig}"


def verify_user_token(secret: str, token: str) -> str | None:
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "act":
        return None
    good = _b64u(hmac.new(secret.encode(), f"act.{parts[1]}".encode(), hashlib.sha256).digest()[:24])
    return f"user:{parts[1]}" if hmac.compare_digest(good, parts[2]) else None


class SupabaseVerifier:
    """Validates a Supabase access token by asking Supabase Auth (works for any signing algorithm)."""

    def __init__(self, url: str, anon_key: str, *, ttl: float = 60.0, timeout: float = 5.0, clock: Callable[[], float] = time.monotonic):
        self.url, self.key, self.ttl, self.timeout, self.clock = url.rstrip("/"), anon_key, ttl, timeout, clock
        self._cache: dict[str, tuple[float, str | None]] = {}

    def verify(self, token: str) -> str | None:
        k = hashlib.sha256(token.encode()).hexdigest()
        hit = self._cache.get(k)
        if hit and hit[0] > self.clock():
            return hit[1]
        req = urllib.request.Request(f"{self.url}/auth/v1/user", headers={"apikey": self.key, "Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                uid = json.loads(r.read()).get("id")
            result = f"user:{uid}" if uid else None
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                result = None
            else:
                raise AuthUnavailable(f"auth provider returned HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise AuthUnavailable("auth provider unreachable") from e
        if len(self._cache) > 5000:
            self._cache.clear()
        self._cache[k] = (self.clock() + (self.ttl if result else 10.0), result)
        return result


class AuthService:
    def __init__(self, *, allow_anonymous: bool, secret: str | None, verifier: SupabaseVerifier | None):
        self.allow_anonymous, self.secret, self.verifier = allow_anonymous, secret, verifier

    async def authenticate(self, token: str) -> str | None:
        if token.startswith("anon."):
            return verify_anon_token(self.secret, token) if self.allow_anonymous and self.secret else None
        if token.startswith("act."):
            return verify_user_token(self.secret, token) if self.secret else None
        if self.verifier is None:
            return None
        return await asyncio.to_thread(self.verifier.verify, token)


# ---- rate limiting / quotas (in-memory, per instance; honest about it in the docs) ----
class RateLimiter:
    def __init__(self, limit: int, window: float = 60.0, clock: Callable[[], float] = time.monotonic, max_keys: int = 20000):
        self.limit, self.window, self.clock, self.max_keys = limit, window, clock, max_keys
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> tuple[bool, float]:
        now = self.clock()
        if len(self._hits) > self.max_keys:
            self._hits = defaultdict(deque, {k: v for k, v in self._hits.items() if v and now - v[-1] < self.window})
        q = self._hits[key]
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False, max(1.0, self.window - (now - q[0]))
        q.append(now)
        return True, 0.0


class DailyQuota:
    def __init__(self, limit: int, today: Callable[[], str] = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d")):
        self.limit, self.today, self._day, self._n = limit, today, "", defaultdict(int)

    def allow(self, key: str) -> tuple[bool, float]:
        d = self.today()
        if d != self._day:
            self._day, self._n = d, defaultdict(int)
        if self._n[key] >= self.limit:
            return False, 3600.0
        self._n[key] += 1
        return True, 0.0


# ---- log redaction ----
_PATTERNS = [
    (re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]*"), "[jwt]"),
    (re.compile(r"anon\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{20,}"), "[guest-token]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-~+/=]{8,}"), "Bearer [redacted]"),
    (re.compile(r"(?i)((?:api[_-]?key|apikey|secret|token|password|authorization|service[_-]?role[_-]?key)[\"'\s:=]+)[^\s\"',}&]{6,}"), r"\1[redacted]"),
    (re.compile(r"[A-Za-z0-9+/=_\-]{200,}"), "[blob]"),
]


def redact(text: str, secrets: list[str] | None = None) -> str:
    for s in secrets or []:
        if s and len(s) >= 6:
            text = text.replace(s, "[secret]")
    for rx, rep in _PATTERNS:
        text = rx.sub(rep, text)
    return text


class RedactingFilter(logging.Filter):
    def __init__(self, secrets: list[str] | None = None) -> None:
        super().__init__()
        self.secrets = secrets or []

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg, record.args = redact(record.getMessage(), self.secrets), None
        if record.exc_info:
            record.exc_text = redact("".join(traceback.format_exception(*record.exc_info)), self.secrets)
            record.exc_info = None
        return True

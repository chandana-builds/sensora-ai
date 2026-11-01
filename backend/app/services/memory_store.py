"""Persistence contract for Milestone 3 + an in-memory implementation (tests/demo scripts only).

Map your Milestone 1 repository to MemoryStore; supabase/migrations/002_milestone3.sql adds the columns/tables.
All methods are scoped by client_id so one user can never read another's sessions.
"""
from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

MAX_EVIDENCE_PER_SESSION = 5


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore(Protocol):
    def get_session(self, cid: str, sid: str) -> dict[str, Any] | None: ...
    def update_session(self, cid: str, sid: str, **fields: Any) -> dict[str, Any]: ...
    def list_sessions(self, cid: str, limit: int = 50) -> list[dict[str, Any]]: ...
    def delete_session(self, cid: str, sid: str) -> None: ...
    def list_messages(self, cid: str, sid: str, limit: int = 30) -> list[dict[str, Any]]: ...
    def add_message(self, cid: str, sid: str, *, role: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def list_steps(self, cid: str, sid: str) -> list[dict[str, Any]]: ...
    def add_step(self, cid: str, sid: str, **fields: Any) -> dict[str, Any]: ...
    def update_step(self, cid: str, sid: str, step_id: str, **fields: Any) -> dict[str, Any]: ...
    def list_observations(self, cid: str, sid: str) -> list[dict[str, Any]]: ...
    def add_observations(self, cid: str, sid: str, texts: list[str], simulated: bool) -> None: ...
    def save_evidence(self, cid: str, sid: str, data: bytes, note: str, retention_days: int) -> dict[str, Any] | None: ...
    def list_evidence(self, cid: str, sid: str) -> list[dict[str, Any]]: ...
    def delete_evidence(self, cid: str, sid: str) -> int: ...
    def get_preferences(self, cid: str) -> dict[str, Any]: ...
    def set_experience_level(self, cid: str, level: str | None, remember: bool) -> dict[str, Any]: ...


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self.sessions: dict[tuple[str, str], dict[str, Any]] = {}
        self.messages: dict[tuple[str, str], list] = {}
        self.steps: dict[tuple[str, str], list] = {}
        self.obs: dict[tuple[str, str], list] = {}
        self.evidence: dict[tuple[str, str], list] = {}
        self.prefs: dict[str, dict[str, Any]] = {}
        self._ids = itertools.count(1)

    def create_session(self, cid: str, sid: str, **fields: Any) -> dict[str, Any]:
        s = {"id": sid, "created_at": now_iso(), "workflow_state": "problem_reported", "evidence_consent": False,
             "clarify_pending": False, "final_status": None, "safety_events": [], "user_level": None, **fields}
        self.sessions[(cid, sid)] = s
        return s

    def get_session(self, cid, sid):
        s = self.sessions.get((cid, sid))
        return dict(s) if s else None

    def update_session(self, cid, sid, **fields):
        self.sessions[(cid, sid)].update(fields)
        return dict(self.sessions[(cid, sid)])

    def list_sessions(self, cid, limit=50):
        rows = [dict(s) for (c, _), s in self.sessions.items() if c == cid]
        return sorted(rows, key=lambda r: r["created_at"], reverse=True)[:limit]

    def delete_session(self, cid, sid):
        for d in (self.sessions, self.messages, self.steps, self.obs, self.evidence):
            d.pop((cid, sid), None)

    def list_messages(self, cid, sid, limit=30):
        return list(self.messages.get((cid, sid), []))[-limit:]

    def add_message(self, cid, sid, *, role, content, metadata=None):
        m = {"id": f"m{next(self._ids)}", "role": role, "content": content, "metadata": metadata or {}, "created_at": now_iso()}
        self.messages.setdefault((cid, sid), []).append(m)
        return m

    def list_steps(self, cid, sid):
        return [dict(s) for s in self.steps.get((cid, sid), [])]

    def add_step(self, cid, sid, **fields):
        s = {"id": f"s{next(self._ids)}", "created_at": now_iso(), **fields}
        self.steps.setdefault((cid, sid), []).append(s)
        return dict(s)

    def update_step(self, cid, sid, step_id, **fields):
        for s in self.steps.get((cid, sid), []):
            if s["id"] == step_id:
                s.update(fields)
                return dict(s)
        raise KeyError(step_id)

    def list_observations(self, cid, sid):
        return list(self.obs.get((cid, sid), []))

    def add_observations(self, cid, sid, texts, simulated):
        have = {o["text"] for o in self.obs.get((cid, sid), [])}
        for t in texts:
            if t not in have:
                self.obs.setdefault((cid, sid), []).append({"text": t, "simulated": simulated, "created_at": now_iso()})
                have.add(t)

    def save_evidence(self, cid, sid, data, note, retention_days):
        s = self.sessions.get((cid, sid))
        if not s or not s.get("evidence_consent"):
            return None                                   # consent is enforced at the storage layer too
        lst = self.evidence.setdefault((cid, sid), [])
        if len(lst) >= MAX_EVIDENCE_PER_SESSION:
            return None
        row = {"id": f"e{next(self._ids)}", "note": note, "size": len(data), "captured_at": now_iso(),
               "expires_at": (datetime.now(timezone.utc) + timedelta(days=retention_days)).isoformat(), "data": data}
        lst.append(row)
        return {k: v for k, v in row.items() if k != "data"}

    def list_evidence(self, cid, sid):
        return [{k: v for k, v in e.items() if k != "data"} for e in self.evidence.get((cid, sid), [])]

    def delete_evidence(self, cid, sid):
        return len(self.evidence.pop((cid, sid), []))

    def get_preferences(self, cid):
        return dict(self.prefs.get(cid, {"user_level": None, "remember_level": False}))

    def set_experience_level(self, cid, level, remember):
        # Persist only with explicit consent; withdrawing consent erases the saved value.
        self.prefs[cid] = {"user_level": level if remember else None, "remember_level": bool(remember)}
        return dict(self.prefs[cid])

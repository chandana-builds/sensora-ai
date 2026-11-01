"""MemoryStore implementation over a Backend. Every read/write is scoped by `owner`, so a user can never
see another user's data, and a wrong id simply looks like 'not found'."""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .errors import QuotaExceeded

_seq_lock, _last = threading.Lock(), 0
SESSION_FIELDS = ("title", "device_name", "device_model", "problem", "user_level")


def _seq() -> int:
    global _last
    with _seq_lock:
        _last = max(time.time_ns(), _last + 1)
        return _last


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return uuid.uuid4().hex


class DocMemoryStore:
    def __init__(self, backend, *, max_sessions: int = 200, max_messages: int = 500, max_evidence: int = 5) -> None:
        self.b, self.max_sessions, self.max_messages, self.max_evidence = backend, max_sessions, max_messages, max_evidence

    # ---- sessions ----
    @staticmethod
    def _sess(row: dict[str, Any]) -> dict[str, Any]:
        return {"id": row["id"], "created_at": row["created_at"], **row["data"]}

    def new_session(self, owner: str, **fields: Any) -> dict[str, Any]:
        if self.b.count("sessions", {"owner": owner}) >= self.max_sessions:
            raise QuotaExceeded(f"You have reached the limit of {self.max_sessions} sessions. Delete old sessions to continue.")
        data = {"workflow_state": "problem_reported", "evidence_consent": False, "clarify_pending": False, "safety_check_answered": False,
                "final_status": None, "safety_events": [], "user_level": None, "title": None, "device_name": None, "device_model": None,
                "problem": None, **{k: v for k, v in fields.items() if k in SESSION_FIELDS and v}}
        row = self.b.insert("sessions", {"owner": owner, "id": _uid(), "seq": _seq(), "created_at": _now(), "data": data})
        return self._sess(row)

    def get_session(self, cid, sid):
        rows = self.b.select("sessions", {"owner": cid, "id": sid}, limit=1)
        return self._sess(rows[0]) if rows else None

    def update_session(self, cid, sid, **fields):
        rows = self.b.select("sessions", {"owner": cid, "id": sid}, limit=1)
        if not rows:
            raise KeyError(sid)
        data = {**rows[0]["data"], **fields}
        self.b.update("sessions", {"owner": cid, "id": sid}, {"data": data})
        return self._sess({**rows[0], "data": data})

    def list_sessions(self, cid, limit=50):
        return [self._sess(r) for r in self.b.select("sessions", {"owner": cid}, order="seq.desc", limit=limit)]

    def delete_session(self, cid, sid):
        for t in ("messages", "steps", "observations", "evidence"):
            self.b.delete(t, {"owner": cid, "sid": sid})
        return self.b.delete("sessions", {"owner": cid, "id": sid})

    def delete_all(self, owner: str) -> int:
        n = self.b.count("sessions", {"owner": owner})
        for t in ("messages", "steps", "observations", "evidence", "sessions", "prefs"):
            self.b.delete(t, {"owner": owner})
        return n

    # ---- messages / steps / observations ----
    def list_messages(self, cid, sid, limit=30):
        rows = self.b.select("messages", {"owner": cid, "sid": sid}, order="seq.desc", limit=limit)
        return [{"id": r["id"], "role": r["role"], "content": r["content"], "metadata": r["metadata"], "created_at": r["created_at"]} for r in reversed(rows)]

    def add_message(self, cid, sid, *, role, content, metadata=None):
        if self.b.count("messages", {"owner": cid, "sid": sid}) >= self.max_messages:
            raise QuotaExceeded("This session is full. Please start a new session.")
        r = self.b.insert("messages", {"id": _uid(), "owner": cid, "sid": sid, "seq": _seq(), "created_at": _now(), "role": role,
                                       "content": content, "metadata": metadata or {}})
        return {k: r[k] for k in ("id", "role", "content", "metadata", "created_at")}

    def list_steps(self, cid, sid):
        return [{"id": r["id"], "created_at": r["created_at"], **r["data"]} for r in self.b.select("steps", {"owner": cid, "sid": sid}, order="seq.asc")]

    def add_step(self, cid, sid, **fields):
        r = self.b.insert("steps", {"id": _uid(), "owner": cid, "sid": sid, "seq": _seq(), "created_at": _now(), "data": fields})
        return {"id": r["id"], "created_at": r["created_at"], **fields}

    def update_step(self, cid, sid, step_id, **fields):
        rows = self.b.select("steps", {"owner": cid, "sid": sid, "id": step_id}, limit=1)
        if not rows:
            raise KeyError(step_id)
        data = {**rows[0]["data"], **fields}
        self.b.update("steps", {"owner": cid, "sid": sid, "id": step_id}, {"data": data})
        return {"id": step_id, "created_at": rows[0]["created_at"], **data}

    def list_observations(self, cid, sid):
        return [{"text": r["text"], "simulated": r["simulated"], "created_at": r["created_at"]}
                for r in self.b.select("observations", {"owner": cid, "sid": sid}, order="seq.asc")]

    def add_observations(self, cid, sid, texts, simulated):
        have = {o["text"] for o in self.list_observations(cid, sid)}
        for t in texts:
            if t not in have:
                self.b.insert("observations", {"id": _uid(), "owner": cid, "sid": sid, "seq": _seq(), "created_at": _now(), "text": t[:300], "simulated": bool(simulated)})
                have.add(t)

    # ---- consented evidence (frames only) ----
    def save_evidence(self, cid, sid, data, note, retention_days):
        s = self.get_session(cid, sid)
        if not s or not s.get("evidence_consent"):
            return None                                   # consent enforced at the storage layer too
        if self.b.count("evidence", {"owner": cid, "sid": sid}) >= self.max_evidence:
            return None
        now = datetime.now(timezone.utc)
        row = {"id": _uid(), "owner": cid, "sid": sid, "seq": _seq(), "note": note[:200], "size": len(data), "captured_at": now.isoformat(),
               "expires_at": (now + timedelta(days=retention_days)).isoformat(), "data": data}
        self.b.insert("evidence", row)
        return {k: row[k] for k in ("id", "note", "size", "captured_at", "expires_at")}

    def list_evidence(self, cid, sid):
        return self.b.select("evidence", {"owner": cid, "sid": sid}, order="seq.asc", columns=["id", "note", "size", "captured_at", "expires_at"])

    def delete_evidence(self, cid, sid):
        return self.b.delete("evidence", {"owner": cid, "sid": sid})

    def purge_expired_evidence(self) -> int:
        return self.b.delete("evidence", {"expires_at__lt": _now()})

    # ---- preferences (saved only with consent) ----
    def get_preferences(self, cid):
        rows = self.b.select("prefs", {"owner": cid}, limit=1)
        return {"user_level": rows[0]["user_level"], "remember_level": rows[0]["remember_level"]} if rows else {"user_level": None, "remember_level": False}

    def set_experience_level(self, cid, level, remember):
        self.b.delete("prefs", {"owner": cid})
        if remember and level:
            self.b.insert("prefs", {"owner": cid, "user_level": level, "remember_level": True})
        return self.get_preferences(cid)

    def get_user_settings(self, cid):
        rows = self.b.select("prefs", {"owner": cid}, limit=1)
        base = {
            "experience_level": "beginner",
            "speak_responses": True,
            "speech_rate": 1.0,
            "larger_text": False,
            "high_contrast": False,
            "reduce_motion": False,
            "save_transcripts": True,
            "display_name": "",
        }
        if not rows:
            return base
        r = rows[0]
        d = r.get("data") if isinstance(r.get("data"), dict) else {}
        exp_level = d.get("experience_level") or r.get("user_level") or "beginner"
        return {
            **base,
            **d,
            "experience_level": exp_level,
        }

    def update_user_settings(self, cid, patch: dict):
        cur = self.get_user_settings(cid)
        cur.update(patch)
        self.b.delete("prefs", {"owner": cid})
        lvl = cur.get("experience_level") or "beginner"
        self.b.insert("prefs", {"owner": cid, "user_level": lvl, "remember_level": True, "data": cur})
        return self.get_user_settings(cid)

    # ---- export / health ----
    def export_all(self, owner: str) -> dict[str, Any]:
        out = []
        for s in self.list_sessions(owner, 10_000):
            out.append({"session": s, "messages": self.list_messages(owner, s["id"], 10_000), "steps": self.list_steps(owner, s["id"]),
                        "observations": self.list_observations(owner, s["id"]), "evidence": self.list_evidence(owner, s["id"])})
        return {"exported_at": _now(), "preferences": self.get_preferences(owner), "sessions": out}

    def ping(self) -> None:
        self.b.ping()

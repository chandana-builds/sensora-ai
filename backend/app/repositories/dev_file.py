"""Development persistence adapter: a single JSON file on disk.

For local development ONLY. It is single-process, not safe for multiple
workers, and is not a substitute for Supabase. `/api/health` reports
`database.mode = "development-file"` with a warning so nothing pretends
Supabase is connected.
"""
import copy
import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

from .base import Repository, StorageError, new_id, utcnow_iso

logger = logging.getLogger("sensora.storage.dev")

_EMPTY = {"profiles": {}, "preferences": {}, "sessions": [], "messages": [], "steps": [], "summaries": {}}


class DevFileRepository(Repository):
    def __init__(self, path: str):
        self._path = Path(path)
        self._lock = threading.RLock()
        self._data = self._load()

    # ── persistence ────────────────────────────────────────────
    def _load(self) -> dict:
        if not self._path.exists():
            return copy.deepcopy(_EMPTY)
        try:
            loaded = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(
                f"Dev store {self._path} is unreadable ({exc}). Fix or delete the file."
            ) from exc
        for key, default in _EMPTY.items():
            loaded.setdefault(key, copy.deepcopy(default))
        return loaded

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    # ── meta ───────────────────────────────────────────────────
    def describe(self) -> dict:
        return {
            "mode": "development-file",
            "persistent": True,
            "warning": "Using the local development file store, not Supabase. Do not use in production.",
        }

    def check(self) -> tuple[bool, Optional[str]]:
        return True, None

    # ── profiles & preferences ─────────────────────────────────
    def ensure_profile(self, user_id: str, is_anonymous: bool) -> None:
        with self._lock:
            if user_id not in self._data["profiles"]:
                self._data["profiles"][user_id] = {
                    "id": user_id, "display_name": None,
                    "is_anonymous": is_anonymous, "created_at": utcnow_iso(),
                }
                self._save()

    def get_preferences(self, user_id: str) -> Optional[dict]:
        with self._lock:
            return copy.deepcopy(self._data["preferences"].get(user_id))

    def upsert_preferences(self, user_id: str, values: dict) -> dict:
        with self._lock:
            row = self._data["preferences"].get(user_id, {"user_id": user_id})
            row.update(values)
            row["updated_at"] = utcnow_iso()
            self._data["preferences"][user_id] = row
            self._save()
            return copy.deepcopy(row)

    # ── sessions ───────────────────────────────────────────────
    def create_session(self, user_id: str, values: dict) -> dict:
        with self._lock:
            now = utcnow_iso()
            row = {"id": new_id(), "user_id": user_id, "ended_at": None,
                   "started_at": now, "updated_at": now, **values}
            self._data["sessions"].append(row)
            self._save()
            return copy.deepcopy(row)

    def list_sessions(self, user_id, status, limit, offset):
        with self._lock:
            rows = [s for s in self._data["sessions"]
                    if s["user_id"] == user_id and (status is None or s["status"] == status)]
            rows.sort(key=lambda s: s["started_at"], reverse=True)
            return copy.deepcopy(rows[offset: offset + limit])

    def _find_session(self, user_id: str, session_id: str) -> Optional[dict]:
        for s in self._data["sessions"]:
            if s["id"] == session_id and s["user_id"] == user_id:
                return s
        return None

    def get_session(self, user_id, session_id):
        with self._lock:
            return copy.deepcopy(self._find_session(user_id, session_id))

    def update_session(self, user_id, session_id, values):
        with self._lock:
            row = self._find_session(user_id, session_id)
            if row is None:
                return None
            row.update(values)
            row["updated_at"] = utcnow_iso()
            self._save()
            return copy.deepcopy(row)

    def _drop_children(self, session_ids: set[str]) -> None:
        for key in ("messages", "steps"):
            self._data[key] = [r for r in self._data[key] if r["session_id"] not in session_ids]
        for sid in session_ids:
            self._data["summaries"].pop(sid, None)

    def delete_session(self, user_id, session_id) -> bool:
        with self._lock:
            if self._find_session(user_id, session_id) is None:
                return False
            self._data["sessions"] = [s for s in self._data["sessions"] if s["id"] != session_id]
            self._drop_children({session_id})
            self._save()
            return True

    def delete_all_sessions(self, user_id) -> int:
        with self._lock:
            ids = {s["id"] for s in self._data["sessions"] if s["user_id"] == user_id}
            self._data["sessions"] = [s for s in self._data["sessions"] if s["id"] not in ids]
            self._drop_children(ids)
            self._save()
            return len(ids)

    # ── messages / steps / summaries ───────────────────────────
    def add_message(self, session_id, values):
        with self._lock:
            row = {"id": new_id(), "session_id": session_id, "created_at": utcnow_iso(), **values}
            self._data["messages"].append(row)
            self._save()
            return copy.deepcopy(row)

    def list_messages(self, session_id):
        with self._lock:
            rows = [m for m in self._data["messages"] if m["session_id"] == session_id]
            rows.sort(key=lambda m: m["created_at"])
            return copy.deepcopy(rows)

    def add_step(self, session_id, values):
        with self._lock:
            existing = [s for s in self._data["steps"] if s["session_id"] == session_id]
            now = utcnow_iso()
            row = {"id": new_id(), "session_id": session_id,
                   "step_number": max((s["step_number"] for s in existing), default=0) + 1,
                   "status": "pending", "verification": "not_verified", "outcome_note": None,
                   "created_at": now, "updated_at": now, **values}
            self._data["steps"].append(row)
            self._save()
            return copy.deepcopy(row)

    def list_steps(self, session_id):
        with self._lock:
            rows = [s for s in self._data["steps"] if s["session_id"] == session_id]
            rows.sort(key=lambda s: s["step_number"])
            return copy.deepcopy(rows)

    def update_step(self, session_id, step_id, values):
        with self._lock:
            for s in self._data["steps"]:
                if s["id"] == step_id and s["session_id"] == session_id:
                    s.update(values)
                    s["updated_at"] = utcnow_iso()
                    self._save()
                    return copy.deepcopy(s)
            return None

    def upsert_summary(self, session_id, values):
        with self._lock:
            now = utcnow_iso()
            row = self._data["summaries"].get(
                session_id, {"session_id": session_id, "created_at": now})
            row.update(values)
            row["updated_at"] = now
            self._data["summaries"][session_id] = row
            self._save()
            return copy.deepcopy(row)

    def get_summary(self, session_id):
        with self._lock:
            return copy.deepcopy(self._data["summaries"].get(session_id))

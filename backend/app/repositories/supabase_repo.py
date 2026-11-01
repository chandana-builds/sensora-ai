"""Supabase PostgreSQL adapter using the PostgREST HTTP API.

Uses the SERVICE ROLE key, which bypasses row-level security. Therefore every
query here is explicitly scoped by user_id, and the key must stay server-side.
Schema: supabase/migrations/*.sql
"""
import logging
from typing import Any, Optional

import httpx

from .base import Repository, StorageError, new_id, utcnow_iso

logger = logging.getLogger("sensora.storage.supabase")


class SupabaseRepository(Repository):
    def __init__(self, url: str, service_role_key: str, timeout: float = 10.0):
        self._client = httpx.Client(
            base_url=f"{url.rstrip('/')}/rest/v1",
            headers={"apikey": service_role_key, "Authorization": f"Bearer {service_role_key}",
                     "Content-Type": "application/json"},
            timeout=timeout,
        )

    # ── low-level helpers ──────────────────────────────────────
    def _req(self, method: str, table: str, *, params: Optional[dict] = None,
             json: Any = None, prefer: Optional[str] = None) -> Any:
        headers = {"Prefer": prefer} if prefer else {}
        try:
            resp = self._client.request(method, f"/{table}", params=params, json=json, headers=headers)
        except httpx.HTTPError as exc:
            logger.error("Supabase request failed: %s", exc)
            raise StorageError("Could not reach Supabase.") from exc
        if resp.status_code >= 400:
            logger.error("Supabase %s %s -> %s %s", method, table, resp.status_code, resp.text[:300])
            raise StorageError(f"Supabase returned {resp.status_code} for {table}.")
        return resp.json() if resp.content else []

    def _select(self, table: str, params: dict) -> list[dict]:
        return self._req("GET", table, params=params)

    def _insert(self, table: str, row: dict) -> dict:
        return self._req("POST", table, json=row, prefer="return=representation")[0]

    def _patch(self, table: str, filters: dict, values: dict) -> Optional[dict]:
        rows = self._req("PATCH", table, params=filters, json=values, prefer="return=representation")
        return rows[0] if rows else None

    def _delete(self, table: str, filters: dict) -> int:
        return len(self._req("DELETE", table, params=filters, prefer="return=representation"))

    @staticmethod
    def _eq(**kw: str) -> dict:
        return {k: f"eq.{v}" for k, v in kw.items()}

    # ── meta ───────────────────────────────────────────────────
    def describe(self) -> dict:
        return {"mode": "supabase", "persistent": True, "warning": None}

    def check(self) -> tuple[bool, Optional[str]]:
        try:
            self._select("profiles", {"select": "id", "limit": "1"})
            return True, None
        except StorageError as exc:
            return False, str(exc)

    # ── profiles & preferences ─────────────────────────────────
    def ensure_profile(self, user_id: str, is_anonymous: bool) -> None:
        self._req("POST", "profiles", params={"on_conflict": "id"},
                  json={"id": user_id, "is_anonymous": is_anonymous},
                  prefer="resolution=ignore-duplicates,return=minimal")

    def get_preferences(self, user_id):
        rows = self._select("user_preferences", {"select": "*", **self._eq(user_id=user_id)})
        return rows[0] if rows else None

    def upsert_preferences(self, user_id, values):
        row = {"user_id": user_id, **values, "updated_at": utcnow_iso()}
        return self._req("POST", "user_preferences", params={"on_conflict": "user_id"}, json=row,
                         prefer="resolution=merge-duplicates,return=representation")[0]

    # ── sessions ───────────────────────────────────────────────
    def create_session(self, user_id, values):
        return self._insert("troubleshooting_sessions", {"id": new_id(), "user_id": user_id, **values})

    def list_sessions(self, user_id, status, limit, offset):
        params = {"select": "*", **self._eq(user_id=user_id), "order": "started_at.desc",
                  "limit": str(limit), "offset": str(offset)}
        if status:
            params["status"] = f"eq.{status}"
        return self._select("troubleshooting_sessions", params)

    def get_session(self, user_id, session_id):
        rows = self._select("troubleshooting_sessions",
                            {"select": "*", **self._eq(id=session_id, user_id=user_id)})
        return rows[0] if rows else None

    def update_session(self, user_id, session_id, values):
        return self._patch("troubleshooting_sessions", self._eq(id=session_id, user_id=user_id), values)

    def delete_session(self, user_id, session_id) -> bool:
        return self._delete("troubleshooting_sessions", self._eq(id=session_id, user_id=user_id)) > 0

    def delete_all_sessions(self, user_id) -> int:
        return self._delete("troubleshooting_sessions", self._eq(user_id=user_id))

    # ── children (ON DELETE CASCADE handles cleanup) ───────────
    def add_message(self, session_id, values):
        return self._insert("conversation_messages", {"id": new_id(), "session_id": session_id, **values})

    def list_messages(self, session_id):
        return self._select("conversation_messages",
                            {"select": "*", **self._eq(session_id=session_id), "order": "created_at.asc"})

    def add_step(self, session_id, values):
        last = self._select("troubleshooting_steps",
                            {"select": "step_number", **self._eq(session_id=session_id),
                             "order": "step_number.desc", "limit": "1"})
        number = (last[0]["step_number"] if last else 0) + 1
        return self._insert("troubleshooting_steps",
                            {"id": new_id(), "session_id": session_id, "step_number": number, **values})

    def list_steps(self, session_id):
        return self._select("troubleshooting_steps",
                            {"select": "*", **self._eq(session_id=session_id), "order": "step_number.asc"})

    def update_step(self, session_id, step_id, values):
        return self._patch("troubleshooting_steps", self._eq(id=step_id, session_id=session_id), values)

    def upsert_summary(self, session_id, values):
        row = {"session_id": session_id, **values, "updated_at": utcnow_iso()}
        return self._req("POST", "session_summaries", params={"on_conflict": "session_id"}, json=row,
                         prefer="resolution=merge-duplicates,return=representation")[0]

    def get_summary(self, session_id):
        rows = self._select("session_summaries", {"select": "*", **self._eq(session_id=session_id)})
        return rows[0] if rows else None

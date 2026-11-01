"""Minimal persistence contract the orchestrator needs.

Wire your Milestone 1 repository to this Protocol (see docs/MILESTONE2.md). InMemoryStore is
for tests only; it is not used by the app unless you assign it explicitly.
"""
from __future__ import annotations

import itertools
from typing import Any, Protocol


class ConversationStore(Protocol):
    def get_session(self, client_id: str, session_id: str) -> dict[str, Any] | None: ...
    def list_messages(self, client_id: str, session_id: str, limit: int = 30) -> list[dict[str, Any]]: ...
    def add_message(self, client_id: str, session_id: str, *, role: str, content: str,
                    metadata: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def add_step(self, client_id: str, session_id: str, *, title: str, instruction: str,
                 expected_result: str = "") -> dict[str, Any]: ...


class InMemoryStore:
    def __init__(self) -> None:
        self.sessions: dict[tuple[str, str], dict[str, Any]] = {}
        self.messages: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.steps: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._ids = itertools.count(1)

    def create_session(self, client_id: str, session_id: str, **fields: Any) -> None:
        self.sessions[(client_id, session_id)] = {"id": session_id, **fields}

    def get_session(self, client_id, session_id):
        return self.sessions.get((client_id, session_id))

    def list_messages(self, client_id, session_id, limit=30):
        return self.messages.get((client_id, session_id), [])[-limit:]

    def add_message(self, client_id, session_id, *, role, content, metadata=None):
        m = {"id": f"m{next(self._ids)}", "role": role, "content": content, "metadata": metadata or {}}
        self.messages.setdefault((client_id, session_id), []).append(m)
        return m

    def add_step(self, client_id, session_id, *, title, instruction, expected_result=""):
        s = {"id": f"s{next(self._ids)}", "title": title, "instruction": instruction,
             "expected_result": expected_result, "status": "awaiting_user"}
        self.steps.setdefault((client_id, session_id), []).append(s)
        return s


class RepositoryAdapter:
    """Adapts Sensora's Milestone 1 Repository to the ConversationStore protocol."""

    def __init__(self, repo_provider: Any) -> None:
        self._repo_provider = repo_provider

    @property
    def repo(self) -> Any:
        return self._repo_provider() if callable(self._repo_provider) else self._repo_provider

    def get_session(self, client_id: str, session_id: str) -> dict[str, Any] | None:
        try:
            s = self.repo.get_session(client_id, session_id)
        except Exception:
            return None
        if not s:
            return None
        return {
            **s,
            "device": s.get("device_name") or "unknown",
            "problem": s.get("problem_description") or s.get("title") or "unknown",
            "user_level": s.get("experience_level") or "beginner",
        }

    def list_messages(self, client_id: str, session_id: str, limit: int = 30) -> list[dict[str, Any]]:
        s = self.repo.get_session(client_id, session_id)
        if not s:
            return []
        msgs = self.repo.list_messages(session_id)
        return msgs[-limit:]

    def add_message(self, client_id: str, session_id: str, *, role: str, content: str,
                    metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        values = {
            "role": role,
            "content": content,
            "input_mode": (metadata or {}).get("input_mode", "text"),
            "safety_level": (metadata or {}).get("structured", {}).get("safety_status", "ok") if metadata else "ok",
        }
        if metadata:
            values["metadata"] = metadata
        return self.repo.add_message(session_id, values)

    def add_step(self, client_id: str, session_id: str, *, title: str, instruction: str,
                 expected_result: str = "") -> dict[str, Any]:
        combined = f"{title}: {instruction}" if title and not instruction.startswith(title) else instruction
        if expected_result:
            combined = f"{combined} (Expected: {expected_result})"
        values = {
            "instruction": combined,
            "status": "pending",
            "verification": "not_verified",
        }
        return self.repo.add_step(session_id, values)


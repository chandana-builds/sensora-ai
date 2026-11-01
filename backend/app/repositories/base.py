"""Repository interface. Routes depend only on this, never on a concrete database."""
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StorageError(Exception):
    """Raised when the underlying store fails (maps to HTTP 502)."""


class Repository(ABC):
    @abstractmethod
    def describe(self) -> dict: ...

    @abstractmethod
    def check(self) -> tuple[bool, Optional[str]]:
        """Return (connected, error message)."""

    # profiles & preferences
    @abstractmethod
    def ensure_profile(self, user_id: str, is_anonymous: bool) -> None: ...
    @abstractmethod
    def get_preferences(self, user_id: str) -> Optional[dict]: ...
    @abstractmethod
    def upsert_preferences(self, user_id: str, values: dict) -> dict: ...

    # sessions (always scoped by user_id)
    @abstractmethod
    def create_session(self, user_id: str, values: dict) -> dict: ...
    @abstractmethod
    def list_sessions(self, user_id: str, status: Optional[str], limit: int, offset: int) -> list[dict]: ...
    @abstractmethod
    def get_session(self, user_id: str, session_id: str) -> Optional[dict]: ...
    @abstractmethod
    def update_session(self, user_id: str, session_id: str, values: dict) -> Optional[dict]: ...
    @abstractmethod
    def delete_session(self, user_id: str, session_id: str) -> bool: ...
    @abstractmethod
    def delete_all_sessions(self, user_id: str) -> int: ...

    # children (caller must have verified session ownership)
    @abstractmethod
    def add_message(self, session_id: str, values: dict) -> dict: ...
    @abstractmethod
    def list_messages(self, session_id: str) -> list[dict]: ...
    @abstractmethod
    def add_step(self, session_id: str, values: dict) -> dict: ...
    @abstractmethod
    def list_steps(self, session_id: str) -> list[dict]: ...
    @abstractmethod
    def update_step(self, session_id: str, step_id: str, values: dict) -> Optional[dict]: ...
    @abstractmethod
    def upsert_summary(self, session_id: str, values: dict) -> dict: ...
    @abstractmethod
    def get_summary(self, session_id: str) -> Optional[dict]: ...

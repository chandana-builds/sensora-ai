from .backends import PostgRESTBackend, SQLiteBackend
from .docstore import DocMemoryStore
from .errors import QuotaExceeded, StoreError, StoreUnavailable


def build_store(s) -> DocMemoryStore:
    """s: config.Settings"""
    if s.storage_backend == "supabase":
        backend = PostgRESTBackend(s.supabase_url, s.supabase_service_key)
    elif s.storage_backend == "sqlite":
        backend = SQLiteBackend(s.sqlite_path)
    else:
        backend = SQLiteBackend(":memory:")
    return DocMemoryStore(backend, max_sessions=s.max_sessions_per_user, max_messages=s.max_messages_per_session)


__all__ = ["build_store", "DocMemoryStore", "SQLiteBackend", "PostgRESTBackend", "QuotaExceeded", "StoreError", "StoreUnavailable"]

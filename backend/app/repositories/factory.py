import logging
from functools import lru_cache

from ..config import get_settings
from .base import Repository
from .dev_file import DevFileRepository
from .supabase_repo import SupabaseRepository

logger = logging.getLogger("sensora.storage")


@lru_cache
def get_repository() -> Repository:
    s = get_settings()
    mode = s.storage_backend
    if mode == "supabase" and not s.supabase_configured:
        raise RuntimeError(
            "STORAGE_BACKEND=supabase but SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set."
        )
    if mode == "supabase" or (mode == "auto" and s.supabase_configured):
        logger.info("Storage: Supabase")
        return SupabaseRepository(s.supabase_url, s.supabase_service_role_key)
    if s.app_env == "production":
        logger.warning("Production environment is using the development file store!")
    logger.warning("Storage: DEVELOPMENT FILE STORE at %s (Supabase is NOT connected)", s.dev_data_path)
    return DevFileRepository(s.dev_data_path)

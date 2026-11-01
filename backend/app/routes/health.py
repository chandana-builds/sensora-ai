from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from .. import __version__
from ..ai.provider import get_ai_status
from ..config import Settings, get_settings
from ..deps import get_repo
from ..repositories.base import Repository
from ..schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(settings: Settings = Depends(get_settings), repo: Repository = Depends(get_repo)):
    connected, error = repo.check()
    return HealthOut(
        status="ok" if connected else "degraded",
        version=__version__,
        environment=settings.app_env,
        time=datetime.now(timezone.utc),
        database={**repo.describe(), "connected": connected, "error": error},
        ai=get_ai_status().to_dict(),
        auth={"mode": settings.auth_mode},
    )

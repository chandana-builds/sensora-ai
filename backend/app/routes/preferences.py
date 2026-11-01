from fastapi import APIRouter, Depends

from ..deps import Ctx, get_ctx
from ..schemas import DEFAULT_PREFERENCES, PreferencesOut, PreferencesUpdate

router = APIRouter(tags=["preferences"])


def _merged(stored: dict | None) -> PreferencesOut:
    data = {**DEFAULT_PREFERENCES, **{k: v for k, v in (stored or {}).items() if k in DEFAULT_PREFERENCES}}
    return PreferencesOut(**data, updated_at=(stored or {}).get("updated_at"))


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(ctx: Ctx = Depends(get_ctx)):
    return _merged(ctx.repo.get_preferences(ctx.user.id))


@router.patch("/preferences", response_model=PreferencesOut)
def update_preferences(body: PreferencesUpdate, ctx: Ctx = Depends(get_ctx)):
    changes = body.model_dump(exclude_none=True)
    if not changes:
        return _merged(ctx.repo.get_preferences(ctx.user.id))
    return _merged(ctx.repo.upsert_preferences(ctx.user.id, changes))

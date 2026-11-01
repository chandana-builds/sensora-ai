import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..deps import Ctx, get_ctx
from ..routes.preferences import _merged

router = APIRouter(tags=["account"])


@router.get("/me/export")
def export_my_data(ctx: Ctx = Depends(get_ctx)):
    """Everything stored for the caller, as a downloadable JSON file."""
    sessions = []
    offset = 0
    while True:
        page = ctx.repo.list_sessions(ctx.user.id, None, 100, offset)
        for s in page:
            sessions.append({**s, "messages": ctx.repo.list_messages(s["id"]),
                             "steps": ctx.repo.list_steps(s["id"]),
                             "summary": ctx.repo.get_summary(s["id"])})
        if len(page) < 100:
            break
        offset += 100
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "preferences": _merged(ctx.repo.get_preferences(ctx.user.id)).model_dump(mode="json"),
        "sessions": sessions,
    }
    return Response(
        content=json.dumps(payload, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="sensora-export.json"'},
    )

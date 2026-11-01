from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..deps import current_user

router = APIRouter(tags=["sessions"])


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    device_name: str | None = Field(default=None, max_length=80)
    problem: str | None = Field(default=None, max_length=4000)
    problem_description: str | None = Field(default=None, max_length=4000)
    user_level: Literal["beginner", "experienced"] | None = None
    experience_level: Literal["beginner", "experienced"] | None = None


def _store(request: Request):
    return request.app.state.memory_store


def _public(s: dict) -> dict:
    return {k: v for k, v in s.items() if k not in ("summary",)}


@router.post("/sessions", status_code=201)
async def create_session(body: SessionCreate, request: Request, cid: str = Depends(current_user)):
    st = _store(request)
    prefs = st.get_preferences(cid)
    prob = body.problem or body.problem_description
    lvl = body.user_level or body.experience_level or prefs.get("user_level")
    title = body.title or (body.device_name and f"{body.device_name} troubleshooting")
    raw = st.new_session(cid, title=title, device_name=body.device_name, problem=prob, user_level=lvl)
    pub = _public(raw)
    return {
        **pub,
        "problem_description": prob,
        "experience_level": lvl or "beginner",
        "status": "active",
        "started_at": pub["created_at"],
        "safety": {"level": "ok", "categories": [], "guidance": []},
    }


@router.get("/sessions")
async def list_sessions(request: Request, limit: int = 50, cid: str = Depends(current_user)):
    return {"sessions": [_public(s) for s in _store(request).list_sessions(cid, max(1, min(limit, 200)))]}


@router.get("/sessions/{sid}")
async def get_session(sid: str, request: Request, cid: str = Depends(current_user)):
    s = _store(request).get_session(cid, sid)
    if s is None:
        raise HTTPException(404, "Session not found.")      # same answer for "missing" and "someone else's"
    messages = _store(request).list_messages(cid, sid, 200)
    steps = _store(request).list_steps(cid, sid)
    return {
        **s,
        "problem_description": s.get("problem"),
        "experience_level": s.get("user_level") or "beginner",
        "status": "active" if not s.get("final_status") and s.get("workflow_state") != "resolved" else (s.get("final_status") or "resolved"),
        "started_at": s.get("created_at"),
        "messages": messages,
        "steps": steps,
        "summary": None,
    }


@router.delete("/sessions/{sid}", status_code=204)
async def delete_session(sid: str, request: Request, cid: str = Depends(current_user)):
    if not _store(request).delete_session(cid, sid):
        raise HTTPException(404, "Session not found.")


@router.get("/me/export")
async def export_me(request: Request, cid: str = Depends(current_user)):
    return _store(request).export_all(cid)


@router.delete("/me/data")
async def delete_my_data(request: Request, cid: str = Depends(current_user)):
    return {"deleted_sessions": _store(request).delete_all(cid)}


@router.get("/preferences")
async def get_preferences(request: Request, cid: str = Depends(current_user)):
    return _store(request).get_user_settings(cid)


@router.patch("/preferences")
async def update_preferences(patch: dict, request: Request, cid: str = Depends(current_user)):
    return _store(request).update_user_settings(cid, patch)


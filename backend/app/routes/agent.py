"""Milestone 3 routes. Mount: app.include_router(agent_router, prefix="/api")

Wiring (docs/MILESTONE3.md):
  app.state.memory_store = <object implementing services.memory_store.MemoryStore>
Providers come from build_providers_v3 (demo reasoner includes verification verdicts).
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..ai.base import ProviderError, ProviderNotConfigured
from ..ai.config import load_ai_settings
from ..ai.demo_provider_v3 import build_providers_v3
from ..schemas_m3 import AgentTurnRequest, CompleteRequest, ConsentRequest, ExportRequest, LevelRequest
from ..services.agent_orchestrator import AgentOrchestrator
from ..services.errors import BadTurn, SessionNotFound
from ..services.handoff import PATHWAYS
from ..deps import current_user, user_with_quota
from .live import _http
from ..services.summary import summary_markdown

log = logging.getLogger("sensora.agent.routes")
router = APIRouter(tags=["agent"])
RETENTION_DAYS = int(os.environ.get("EVIDENCE_RETENTION_DAYS", "30"))


def _orch(request: Request) -> AgentOrchestrator:
    store = getattr(request.app.state, "memory_store", None)
    if store is None:
        raise HTTPException(501, "memory_store is not wired (see docs/MILESTONE3.md).")
    p = getattr(request.app.state, "ai_providers_v3", None)
    if p is None:
        try:
            p = request.app.state.ai_providers_v3 = build_providers_v3(load_ai_settings())
        except ProviderNotConfigured as exc:
            raise HTTPException(503, exc.message) from exc
    return AgentOrchestrator(store, p, retention_days=RETENTION_DAYS)


def _guard(fn):
    try:
        return fn()
    except SessionNotFound:
        raise HTTPException(404, "Session not found.")


@router.post("/sessions/{sid}/agent/turn")
async def agent_turn(sid: str, body: AgentTurnRequest, request: Request, cid: str = Depends(user_with_quota)):
    o = _orch(request)
    try:
        return await o.handle_turn(cid, sid, body)
    except SessionNotFound:
        raise HTTPException(404, "Session not found.")
    except BadTurn as exc:
        raise HTTPException(422, str(exc))
    except ProviderError as exc:
        raise _http(exc)


@router.get("/sessions/{sid}/memory")
async def memory(sid: str, request: Request, cid: str = Depends(current_user)):
    """Everything needed to reopen a session in the UI."""
    o = _orch(request)
    s = _guard(lambda: o._session(cid, sid))
    return {"session": {k: v for k, v in s.items() if k != "summary"}, "messages": o.store.list_messages(cid, sid, 200),
            "steps": o.store.list_steps(cid, sid), "observations": o.store.list_observations(cid, sid),
            "evidence": o.store.list_evidence(cid, sid)}


@router.post("/sessions/{sid}/complete")
async def complete(sid: str, body: CompleteRequest, request: Request, cid: str = Depends(current_user)):
    o = _orch(request)
    return _guard(lambda: o.complete(cid, sid, body.status))


@router.get("/sessions/{sid}/summary")
async def summary(sid: str, request: Request, cid: str = Depends(current_user)):
    o = _orch(request)
    s = _guard(lambda: o.summary(cid, sid))
    return {"summary": s, "markdown": summary_markdown(s)}


@router.get("/sessions/{sid}/related")
async def related(sid: str, request: Request, cid: str = Depends(current_user)):
    o = _orch(request)
    return {"related": _guard(lambda: o.related(cid, sid))}


@router.get("/sessions/{sid}/handoff")
async def handoff_preview(sid: str, request: Request, pathway: str = "local_technician", include_evidence: bool = False,
                          cid: str = Depends(current_user)):
    if pathway not in PATHWAYS:
        raise HTTPException(422, "pathway must be remote_expert or local_technician")
    o = _orch(request)
    return _guard(lambda: o.handoff(cid, sid, pathway, include_evidence))   # preview only: nothing is shared


@router.post("/sessions/{sid}/handoff/export")
async def handoff_export(sid: str, body: ExportRequest, request: Request, cid: str = Depends(current_user)):
    o = _orch(request)
    try:
        content, mime, name = _guard(lambda: o.export(cid, sid, pathway=body.pathway, include_evidence=body.include_evidence,
                                                      consent_to_share=body.consent_to_share, fmt=body.format))
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    return Response(content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.put("/sessions/{sid}/consent")
async def set_consent(sid: str, body: ConsentRequest, request: Request, cid: str = Depends(current_user)):
    o = _orch(request)
    _guard(lambda: o._session(cid, sid))
    o.store.update_session(cid, sid, evidence_consent=body.evidence_consent)
    deleted = 0 if body.evidence_consent else o.store.delete_evidence(cid, sid)   # withdrawing consent erases stored frames
    return {"evidence_consent": body.evidence_consent, "deleted_frames": deleted, "retention_days": RETENTION_DAYS, "max_frames": 5}


@router.get("/sessions/{sid}/evidence")
async def list_evidence(sid: str, request: Request, cid: str = Depends(current_user)):
    o = _orch(request)
    _guard(lambda: o._session(cid, sid))
    return {"evidence": o.store.list_evidence(cid, sid), "retention_days": RETENTION_DAYS}


@router.delete("/sessions/{sid}/evidence")
async def delete_evidence(sid: str, request: Request, cid: str = Depends(current_user)):
    o = _orch(request)
    _guard(lambda: o._session(cid, sid))
    return {"deleted_frames": o.store.delete_evidence(cid, sid)}


@router.get("/preferences/experience")
async def get_level(request: Request, cid: str = Depends(current_user)):
    return _orch(request).store.get_preferences(cid)


@router.put("/preferences/experience")
async def put_level(body: LevelRequest, request: Request, cid: str = Depends(current_user)):
    return _orch(request).store.set_experience_level(cid, body.level, body.remember)

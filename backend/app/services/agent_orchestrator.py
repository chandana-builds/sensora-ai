"""Milestone 3 turn orchestration: persists everything and runs the closed-loop engine."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..ai.base import ProviderError, VisionResult
from ..ai.factory import Providers
from . import engine, recurrence, workflow as wf
from .audio import AudioError, decode_jpeg_frames
from .handoff import build_handoff, handoff_html, handoff_markdown
from .memory_store import MemoryStore, now_iso
from .errors import BadTurn, SessionNotFound
from .prompt import REPAIR_PROMPT
from .prompt_m3 import SYSTEM_PROMPT_M3
from . import safety_engine as se
from .summary import build_summary

log = logging.getLogger("sensora.agent")
LEVELS = ("beginner", "experienced")
OPEN_STEP = ("awaiting_user", "awaiting_verification")


class AgentOrchestrator:
    def __init__(self, store: MemoryStore, providers: Providers, *, retention_days: int = 30) -> None:
        self.store, self.p, self.retention_days = store, providers, retention_days

    async def _db(self, fn, *a, **kw):
        return await asyncio.to_thread(fn, *a, **kw)

    def _session(self, cid, sid):
        s = self.store.get_session(cid, sid)
        if s is None:
            raise SessionNotFound(sid)
        return s

    async def handle_turn(self, cid: str, sid: str, req: Any) -> dict[str, Any]:
        session = await self._db(self._session, cid, sid)
        try:
            frames = decode_jpeg_frames(list(getattr(req, "frames", []) or []))
        except AudioError as exc:
            raise BadTurn(str(exc)) from exc
        text = req.text.strip()
        reported_done = bool(getattr(req, "reported_step_done", False))
        warnings: list[str] = []

        if session.get("workflow_state") == wf.COMPLETED:        # reopening a finished session
            session = await self._db(self.store.update_session, cid, sid, workflow_state=wf.INFO, final_status=None)
        level = getattr(req, "user_level", None) or session.get("user_level")
        if level is None:
            level = (await self._db(self.store.get_preferences, cid)).get("user_level")
        if level in LEVELS and level != session.get("user_level"):
            session = await self._db(self.store.update_session, cid, sid, user_level=level)

        prior = await self._db(self.store.list_messages, cid, sid, 20)
        first_turn = not any(m["role"] == "user" for m in prior)
        if first_turn and not session.get("problem"):
            session = await self._db(self.store.update_session, cid, sid, problem=text[:300])
        images = [
            f if f.startswith("data:") else f"data:image/jpeg;base64,{f}"
            for f in (getattr(req, "frames", []) or [])[:3]
        ]
        user_msg = await self._db(self.store.add_message, cid, sid, role="user", content=text,
                                  metadata={"input_mode": getattr(req, "input_mode", "text"), "frames": len(frames),
                                            "images": images, "reported_step_done": reported_done})

        # 1) Safety on the user's own words, before any model call
        d = se.classify_user_text(text)
        pending = bool(session.get("clarify_pending"))
        if d.action == se.STOP:
            return await self._deterministic(cid, sid, user_msg, session, engine.stop_response(d.category), d.category, wf.ESCALATION, warnings)
        if d.action == se.CLARIFY and not pending:
            await self._db(self.store.update_session, cid, sid, clarify_pending=True)
            return await self._deterministic(cid, sid, user_msg, session, engine.clarify_response(), None, wf.INFO, warnings)
        if pending:  # the user has answered the safety check (STOP already returned above)
            await self._db(self.store.update_session, cid, sid, clarify_pending=False, safety_check_answered=True)
            session["clarify_pending"], session["safety_check_answered"], pending = False, True, False

        # 2) Vision (separate capability), consented evidence storage
        vision: VisionResult | None = None
        if frames:
            try:
                vision = await self.p.vision.analyze(frames, context=text)
            except ProviderError as exc:
                log.warning("vision failed: %s", exc.code)
                warnings.append(f"I couldn't analyse the image ({exc.message}). Continuing without it.")
            if session.get("evidence_consent"):
                for f in frames:
                    await self._db(self.store.save_evidence, cid, sid, f, "user-captured frame", self.retention_days)
            if vision and vision.image_quality == "unusable":
                warnings.append("The image was too unclear to use.")

        # 3) Context: active step, steps tried, recurring-issue history
        steps = await self._db(self.store.list_steps, cid, sid)
        active = next((s for s in reversed(steps) if s.get("status") in OPEN_STEP), None)
        context: dict[str, Any] = {
            "user_level": level or "unknown", "device": session.get("device_name") or "unknown",
            "device_model": session.get("device_model") or "unknown", "reported_problem": session.get("problem") or "unknown",
            "user_turn_index": sum(1 for m in prior if m["role"] == "user") + 1, "images_this_turn": len(frames),
            "workflow_state": session.get("workflow_state"), "user_reported_step_done": reported_done,
            "active_step": ({k: active.get(k) for k in ("title", "instruction", "expected_result", "verification_mode")} if active else None),
            "steps_tried": [{"title": s["title"], "outcome": s.get("verification_outcome", "pending")} for s in steps if s is not active],
            "safety_check_answered": bool(session.get("safety_check_answered")),
        }
        if first_turn:
            others = await self._db(self.store.list_sessions, cid, 50)
            rel = recurrence.related_sessions({**session, "problem": session.get("problem") or text}, others)
            if rel:
                by = {s["id"]: await self._db(self.store.list_steps, cid, s["id"]) for _, s in rel}
                context["prior_history"] = recurrence.history_block(rel, by)
        history = [{"role": m["role"], "content": m["content"]} for m in prior if m.get("content") and m["role"] in ("user", "assistant")]
        vis = None if vision is None else {"image_quality": vision.image_quality, "simulated": vision.simulated, "observations": vision.observations}

        # 4) Reason -> engine (one repair attempt if the output is unusable)
        async def run(user_text: str, hist: list[dict[str, str]]):
            raw = await self.p.reasoner.reason(system=SYSTEM_PROMPT_M3, history=hist, user_text=user_text, vision=vision, context=context)
            return raw, engine.apply_turn(raw=raw, session=session, active_step=active, user_reported=reported_done,
                                          frames_count=len(frames) if vision else 0, vision=vis,
                                          simulated_mode=self.p.simulated, clarify_pending=pending)
        try:
            raw, dec = await run(text, history)
        except ValueError as first:
            try:
                raw, dec = await run(REPAIR_PROMPT.format(error=str(first)[:200]), history + [{"role": "user", "content": text}])
            except ValueError as exc:
                raise ProviderError("The AI returned an unusable answer. Please try again.", code="invalid_model_output", status=502) from exc
        prov = raw.get("_provider") or getattr(self.p.reasoner, "name", self.p.mode)
        return await self._persist(cid, sid, user_msg, session, dec, len(frames) if vision else 0, warnings, provider=prov)

    async def _deterministic(self, cid, sid, user_msg, session, resp, category, state, warnings):
        dec = {"response": resp, "state": wf.transition(session.get("workflow_state") or wf.PROBLEM_REPORTED, state),
               "step_update": None, "new_step": None, "outcome": None, "outcome_basis": "none", "visually_verified": False,
               "observations": [], "overridden": True, "safety_category": category, "clarify": category is None,
               "session_updates": {}, "active_step_after": None}
        dec["session_updates"] = {"workflow_state": dec["state"], **({"final_status": "escalated"} if state == wf.ESCALATION else {})}
        return await self._persist(cid, sid, user_msg, session, dec, 0, warnings, provider="deterministic_safety")

    async def _persist(self, cid, sid, user_msg, session, dec, n_frames, warnings, provider: str = "meta") -> dict[str, Any]:
        resp = dec["response"]
        meta = {"structured": resp, "state": dec["state"], "mode": self.p.mode, "simulated": self.p.simulated, "outcome": dec["outcome"], "provider": provider}
        a = await self._db(self.store.add_message, cid, sid, role="assistant", content=resp["assistant_message"], metadata=meta)
        if dec["step_update"]:
            await self._db(self.store.update_step, cid, sid, dec["step_update"]["id"], **dec["step_update"]["fields"])
        step = None
        if dec["new_step"]:
            step = await self._db(self.store.add_step, cid, sid, **dec["new_step"])
        elif dec["active_step_after"]:
            step = next((s for s in await self._db(self.store.list_steps, cid, sid) if s["id"] == dec["active_step_after"]["id"]), None)
        if dec["observations"]:
            await self._db(self.store.add_observations, cid, sid, dec["observations"], self.p.simulated)
        upd = dict(dec["session_updates"])
        if dec["safety_category"]:
            events = list(session.get("safety_events") or [])
            if dec["safety_category"] not in events:
                events.append(dec["safety_category"])
            upd["safety_events"] = events
        await self._db(self.store.update_session, cid, sid, **upd)
        return {"user_message_id": str(user_msg["id"]), "assistant_message_id": str(a["id"]), "response": resp, "mode": self.p.mode,
                "simulated": self.p.simulated, "frames_analyzed": n_frames, "safety_overridden": dec["overridden"], "warnings": warnings,
                "workflow_state": dec["state"], "outcome": dec["outcome"], "visually_verified": dec["visually_verified"],
                "user_reported_complete": bool(step and step.get("user_reported_complete")), "step": step, "provider": provider}

    # ---- summary / lifecycle / handoff -------------------------------------------------
    def summary(self, cid, sid) -> dict[str, Any]:
        s = self._session(cid, sid)
        return build_summary(session=s, messages=self.store.list_messages(cid, sid, 200), steps=self.store.list_steps(cid, sid),
                             observations=self.store.list_observations(cid, sid))

    def complete(self, cid, sid, status: str | None) -> dict[str, Any]:
        s = self._session(cid, sid)
        final = s.get("final_status")
        if status == "unresolved" and not final:
            final = "unresolved"
        elif status == "abandoned" and not final:
            final = "abandoned"
        elif status == "resolved" and not (final or "").startswith("resolved"):
            final = "resolved_unverified"                       # user's word, never auto-verified
        self.store.update_session(cid, sid, workflow_state=wf.COMPLETED, final_status=final)
        summ = self.summary(cid, sid)
        self.store.update_session(cid, sid, summary=summ)
        return summ

    def handoff(self, cid, sid, pathway: str, include_evidence: bool) -> dict[str, Any]:
        s = self._session(cid, sid)
        return build_handoff(session=s, summary=self.summary(cid, sid), messages=self.store.list_messages(cid, sid, 200),
                             steps=self.store.list_steps(cid, sid), evidence=self.store.list_evidence(cid, sid), pathway=pathway,
                             include_evidence=include_evidence, evidence_consent=bool(s.get("evidence_consent")), generated_at=now_iso())

    def export(self, cid, sid, *, pathway: str, include_evidence: bool, consent_to_share: bool, fmt: str) -> tuple[str, str, str]:
        if consent_to_share is not True:
            raise PermissionError("Explicit permission to share is required before exporting the report.")
        h = self.handoff(cid, sid, pathway, include_evidence)
        if fmt == "html":
            return handoff_html(h), "text/html; charset=utf-8", "sensora-handoff.html"
        return handoff_markdown(h), "text/markdown; charset=utf-8", "sensora-handoff.md"

    def related(self, cid, sid):
        s = self._session(cid, sid)
        others = self.store.list_sessions(cid, 50)
        return [{"score": sc, "id": o["id"], "device": o.get("device_name"), "problem": o.get("problem"), "status": o.get("final_status") or o.get("workflow_state"),
                 "steps": [{"title": st["title"], "outcome": st.get("verification_outcome")} for st in self.store.list_steps(cid, o["id"])]}
                for sc, o in recurrence.related_sessions(s, others)]

"""One troubleshooting turn: safety -> persist -> (vision) -> reason -> validate -> gate -> persist."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import ValidationError

from ..ai.base import ProviderError, VisionResult
from ..ai.factory import Providers
from ..schemas_ai import TroubleshootingResponse, TurnRequest, TurnResponse
from .errors import BadTurn, SessionNotFound  # noqa: F401
from .audio import AudioError, decode_jpeg_frames
from .prompt import REPAIR_PROMPT, SYSTEM_PROMPT
from .safety_gate import assess_user_text, screen_response, stop_response
from .store import ConversationStore

log = logging.getLogger("sensora.orchestrator")
HISTORY_LIMIT = 20


class Orchestrator:
    def __init__(self, store: ConversationStore, providers: Providers) -> None:
        self.store, self.p = store, providers

    async def _db(self, fn, *a, **kw):
        return await asyncio.to_thread(fn, *a, **kw)

    async def handle_turn(self, client_id: str, session_id: str, req: TurnRequest) -> TurnResponse:
        session = await self._db(self.store.get_session, client_id, session_id)
        if session is None:
            raise SessionNotFound(session_id)
        try:
            frames = decode_jpeg_frames(req.frames)
        except AudioError as exc:
            raise BadTurn(str(exc)) from exc

        prior = await self._db(self.store.list_messages, client_id, session_id, HISTORY_LIMIT)
        images = [
            f if f.startswith("data:") else f"data:image/jpeg;base64,{f}"
            for f in (getattr(req, "frames", []) or [])[:3]
        ]
        user_msg = await self._db(self.store.add_message, client_id, session_id, role="user", content=req.text,
                                  metadata={"input_mode": req.input_mode, "frames": len(frames), "images": images})
        warnings: list[str] = []

        hazard, label = assess_user_text(req.text)
        if hazard:  # deterministic stop: the model is not consulted
            return await self._finish(client_id, session_id, user_msg, stop_response(label), True, 0, warnings)

        vision: VisionResult | None = None
        if frames:
            try:
                vision = await self.p.vision.analyze(frames, context=req.text)
            except ProviderError as exc:
                log.warning("vision failed: %s", exc.code)
                warnings.append(f"I couldn't analyse the image ({exc.message}). Continuing without it.")
            else:
                if vision.image_quality == "unusable":
                    warnings.append("The image was too unclear to use.")

        history = [{"role": m["role"] if m["role"] in ("user", "assistant") else "assistant",
                    "content": m["content"]} for m in prior if m.get("content")]
        user_turn_index = sum(1 for m in prior if m.get("role") == "user") + 1
        context: dict[str, Any] = {
            "user_level": req.user_level or session.get("user_level") or "unknown",
            "device": session.get("device_name") or session.get("device") or "unknown",
            "reported_problem": session.get("problem") or session.get("title") or "unknown",
            "user_turn_index": user_turn_index, "images_this_turn": len(frames),
        }

        resp = await self._reason_validated(history, req.text, vision, context)
        resp, overridden = screen_response(resp)
        if not frames or (vision and vision.image_quality != "good"):
            if resp.verification_required:  # cannot verify without usable evidence this turn
                resp.verification_required, resp.requires_new_image = True, True
        return await self._finish(client_id, session_id, user_msg, resp, overridden, len(frames) if vision else 0, warnings)

    async def _reason_validated(self, history, text, vision, context) -> TroubleshootingResponse:
        raw = await self.p.reasoner.reason(system=SYSTEM_PROMPT, history=history, user_text=text,
                                           vision=vision, context=context)
        try:
            return TroubleshootingResponse.model_validate(raw)
        except ValidationError as first:
            log.warning("model output failed validation; one repair attempt")
            repair = history + [{"role": "user", "content": text},
                                {"role": "assistant", "content": str(raw)[:1500]}]
            raw2 = await self.p.reasoner.reason(
                system=SYSTEM_PROMPT, history=repair, user_text=REPAIR_PROMPT.format(error=str(first)[:200]),
                vision=vision, context=context)
            try:
                return TroubleshootingResponse.model_validate(raw2)
            except ValidationError as exc:
                raise ProviderError("The AI returned an unusable answer. Please try again.",
                                    code="invalid_model_output", status=502) from exc

    async def _finish(self, client_id, session_id, user_msg, resp, overridden, n_frames, warnings) -> TurnResponse:
        meta = {"structured": resp.model_dump(mode="json"), "mode": self.p.mode, "simulated": self.p.simulated}
        a = await self._db(self.store.add_message, client_id, session_id, role="assistant",
                           content=resp.assistant_message, metadata=meta)
        if resp.current_step:
            await self._db(self.store.add_step, client_id, session_id, title=resp.current_step.title,
                           instruction=resp.current_step.instruction, expected_result=resp.current_step.expected_result)
        return TurnResponse(user_message_id=str(user_msg.get("id")), assistant_message_id=str(a.get("id")),
                            response=resp, mode=self.p.mode, simulated=self.p.simulated,
                            frames_analyzed=n_frames, safety_overridden=overridden, warnings=warnings)

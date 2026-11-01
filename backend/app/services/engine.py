"""Closed-loop turn engine (pure functions): normalise model output -> safety screen -> verify the
previous step -> enforce one instruction at a time -> choose the next workflow state."""
from __future__ import annotations

from typing import Any

from . import safety_engine as se
from . import workflow as wf

VERDICTS = ("succeeded", "failed", "uncertain", "not_applicable")
LEVELS = ("low", "medium", "high")
_STATUS_FOR = {"succeeded": "completed_verified", "user_confirmed": "completed_user_confirmed",
               "simulated_not_verified": "completed_simulated", "failed": "failed",
               "uncertain": "awaiting_verification", "user_reported_unverified": "awaiting_verification"}


def _s(v: Any, n: int) -> str:
    return str(v).strip()[:n] if v is not None else ""


def normalize(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("model output is not an object")
    msg = _s(raw.get("assistant_message"), 900)
    if not msg:
        raise ValueError("assistant_message missing")
    step = raw.get("current_step")
    if isinstance(step, dict) and _s(step.get("instruction"), 400):
        mode = step.get("verification_mode")
        step = {"title": _s(step.get("title"), 80) or "Next step", "instruction": _s(step.get("instruction"), 400),
                "expected_result": _s(step.get("expected_result"), 250),
                "verification_mode": mode if mode in ("visual", "user_confirmation") else "visual"}
    else:
        step = None
    conf = raw.get("confidence") if isinstance(raw.get("confidence"), dict) else {}
    causes = [{"cause": _s(c.get("cause"), 200), "likelihood": c.get("likelihood") if c.get("likelihood") in LEVELS else "low"}
              for c in (raw.get("likely_causes") or [])[:4] if isinstance(c, dict) and _s(c.get("cause"), 200)]
    dev = raw.get("device") if isinstance(raw.get("device"), dict) else {}
    resp = {
        "assistant_message": msg,
        "observations": [_s(o, 200) for o in (raw.get("observations") or [])[:12] if _s(o, 200)],
        "likely_causes": causes,
        "confidence": {"level": conf.get("level") if conf.get("level") in LEVELS else "low", "note": _s(conf.get("note"), 300)},
        "current_step": step,
        "requested_user_action": _s(raw.get("requested_user_action"), 300) or None,
        "requires_new_image": bool(raw.get("requires_new_image")),
        "verification_required": bool(raw.get("verification_required")),
        "safety_status": raw.get("safety_status") if raw.get("safety_status") in ("ok", "caution", "stop") else "ok",
        "escalation_recommended": bool(raw.get("escalation_recommended")),
        "step_verdict": raw.get("step_verdict") if raw.get("step_verdict") in VERDICTS else "not_applicable",
        "step_verdict_evidence": _s(raw.get("step_verdict_evidence"), 300),
        "issue_resolved": bool(raw.get("issue_resolved")),
        "device": {"type": _s(dev.get("type"), 80) or None, "model": _s(dev.get("model"), 80) or None},
    }
    if resp["safety_status"] == "stop" or resp["escalation_recommended"]:
        resp.update(current_step=None, requested_user_action=None, verification_required=False)
    elif step and not resp["requested_user_action"]:
        resp["requested_user_action"] = step["instruction"]
    return resp


def stop_response(category: str | None) -> dict[str, Any]:
    return normalize({"assistant_message": se.stop_message(category), "safety_status": "stop", "escalation_recommended": True,
                      "confidence": {"level": "high", "note": "Safety rule triggered."}})


def clarify_response() -> dict[str, Any]:
    return normalize({"assistant_message": se.CLARIFY_QUESTION, "safety_status": "caution",
                      "confidence": {"level": "low", "note": "Safety check before any instruction."}})


def decide_verification(*, verdict: str, evidence: str, user_reported: bool, evidence_ok: bool,
                        simulated: bool, mode: str = "visual") -> tuple[str, str, bool]:
    """Return (outcome, basis, visually_verified). visually_verified is True ONLY with real, usable
    visual evidence this turn and an evidence statement; a user's word alone never sets it."""
    has_ev = bool(evidence and evidence.strip())
    if verdict == "failed":
        return "failed", ("simulated" if simulated else "visual" if evidence_ok and has_ev else "user_report"), False
    if verdict == "succeeded":
        if simulated:
            return "simulated_not_verified", "none", False
        if evidence_ok and has_ev:
            return "succeeded", "visual", True
    if mode == "user_confirmation" and user_reported and verdict != "uncertain":
        return "user_confirmed", "user_report", False
    if verdict == "uncertain":
        return "uncertain", "none", False
    if user_reported:
        return "user_reported_unverified", "user_report", False
    return ("uncertain" if verdict == "succeeded" else "pending"), "none", False


def apply_turn(*, raw: Any, session: dict[str, Any], active_step: dict[str, Any] | None, user_reported: bool,
               frames_count: int, vision: dict[str, Any] | None, simulated_mode: bool,
               clarify_pending: bool = False) -> dict[str, Any]:
    resp = normalize(raw)
    cur = session.get("workflow_state") or wf.PROBLEM_REPORTED
    overridden, safety_category, clarify = False, None, False

    parts = [resp["assistant_message"], resp["requested_user_action"] or ""]
    if resp["current_step"]:
        parts += [resp["current_step"]["title"], resp["current_step"]["instruction"]]
    joined = " ".join(parts)
    d = se.classify_instruction(joined, clarify_pending=clarify_pending)
    if d.action == se.STOP:
        resp, overridden, safety_category = stop_response(d.category), True, d.category
    elif d.action == se.CLARIFY:
        resp, overridden, clarify = clarify_response(), True, True
    elif se.claims_physical_safety(joined):
        resp["assistant_message"] += " " + se.SAFETY_DISCLAIMER
        if resp["safety_status"] == "ok":
            resp["safety_status"] = "caution"
    if resp["safety_status"] == "stop" and safety_category is None:
        safety_category = "model_flagged"

    halted = resp["safety_status"] == "stop" or resp["escalation_recommended"] or clarify
    resolved = resp["issue_resolved"] and not halted
    step_update = new_step = outcome = None
    outcome_basis, visually = "none", False
    vision_sim = bool(vision and vision.get("simulated"))
    evidence_ok = bool(frames_count > 0 and vision and vision.get("image_quality") == "good" and not vision_sim and not simulated_mode)

    if active_step and not clarify and resp["safety_status"] != "stop":   # still record the step result when escalating
        already = bool(active_step.get("user_reported_complete"))
        outcome, outcome_basis, visually = decide_verification(
            verdict=resp["step_verdict"], evidence=resp["step_verdict_evidence"], user_reported=user_reported or already,
            evidence_ok=evidence_ok, simulated=simulated_mode or vision_sim, mode=active_step.get("verification_mode", "visual"))
        fields: dict[str, Any] = {"user_reported_complete": user_reported or already}
        if outcome != "pending":
            fields.update(visually_verified=visually, verification_outcome=outcome, verification_basis=outcome_basis,
                          verification_note=resp["step_verdict_evidence"][:300], status=_STATUS_FOR[outcome])
        step_update = {"id": active_step["id"], "fields": fields}
        expected = active_step.get("expected_result") or "the result"
        if not resolved and not halted and outcome in ("uncertain", "user_reported_unverified"):
            lead = ("Thanks for telling me you did it. " if outcome == "user_reported_unverified" else "")
            resp.update(assistant_message=f"{lead}I can't confirm that step worked yet. Please capture a clear frame showing: {expected}.",
                        current_step=None, requested_user_action=f"Show me: {expected}", requires_new_image=True,
                        verification_required=True)
        elif not resolved and not halted and outcome == "pending" and resp["current_step"]:
            resp.update(assistant_message=f"Let's finish the current step first: {active_step['instruction']} Tell me or show me when it's done.",
                        current_step=None, requested_user_action=active_step["instruction"])
    if resolved:
        resp.update(current_step=None, requested_user_action=None)
        if outcome != "succeeded" and not simulated_mode:
            resp["assistant_message"] += " You've told me it's working; I haven't been able to verify that visually."
    elif resp["current_step"] and not halted:
        s = resp["current_step"]
        new_step = {**s, "status": "awaiting_user", "user_reported_complete": False, "visually_verified": False,
                    "verification_outcome": "pending", "verification_basis": "none", "simulated": simulated_mode}

    target = wf.choose_target(first_turn=cur == wf.PROBLEM_REPORTED, escalate=halted and not clarify, resolved=resolved,
                              needs_image=resp["requires_new_image"], new_step=new_step is not None,
                              verifying=resp["verification_required"], clarify=clarify)
    state = wf.transition(cur, target)

    obs = [o for o in (vision or {}).get("observations", [])]
    for o in resp["observations"]:  # model observations, minus duplicates of the vision output (e.g. demo prefixes)
        if not any(v in o or o in v for v in obs):
            obs.append(o)
    session_updates: dict[str, Any] = {"workflow_state": state}
    dev = resp["device"]
    if dev["type"]:
        session_updates["device_name"] = dev["type"]
    if dev["model"]:
        session_updates["device_model"] = dev["model"]
    if resolved:
        session_updates["final_status"] = "resolved_verified" if outcome == "succeeded" else "resolved_unverified"
    elif state == wf.ESCALATION:
        session_updates["final_status"] = "escalated"
    active_after = new_step or (active_step if not (outcome in ("succeeded", "failed", "user_confirmed", "simulated_not_verified")) else None)
    return {"response": resp, "state": state, "step_update": step_update, "new_step": new_step, "outcome": outcome,
            "outcome_basis": outcome_basis, "visually_verified": visually, "observations": obs, "overridden": overridden,
            "safety_category": safety_category, "clarify": clarify, "session_updates": session_updates,
            "active_step_after": active_after}

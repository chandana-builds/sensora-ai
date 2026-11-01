"""Deterministic session summary (no model call, so nothing in it is invented)."""
from __future__ import annotations

from typing import Any

from .workflow import ANALYZING, AWAIT_ACTION, AWAIT_IMAGE, COMPLETED, ESCALATION, INFO, OUTCOME_LABELS, PROBLEM_REPORTED, RESOLVED, STATUS_LABELS, VERIFYING

FINAL_LABELS = {"resolved_verified": "Resolved, verified visually", "resolved_unverified": "Resolved, based on your report (not visually verified)",
                "escalated": "Escalated: professional help recommended", "unresolved": "Ended unresolved", "abandoned": "Ended before a result"}
_NEXT = {
    ESCALATION: "Contact a qualified technician, your provider or the manufacturer's service and share the technician report. Don't open the device.",
    RESOLVED: "Keep an eye on it. If it comes back, reopen this session so earlier steps aren't repeated blindly.",
    AWAIT_ACTION: "Try the current step and then tell or show Sensora the result.",
    AWAIT_IMAGE: "Capture a clear frame of the device or the result of your last step.",
    VERIFYING: "Show the result of the last step so it can be checked.",
    INFO: "Answer Sensora's questions about the device and symptoms.", ANALYZING: "Continue the session for the next step.",
    PROBLEM_REPORTED: "Describe the problem and show the device.", COMPLETED: "Reopen the session if the problem returns.",
}


def build_summary(*, session: dict[str, Any], messages: list[dict[str, Any]], steps: list[dict[str, Any]],
                  observations: list[dict[str, Any]]) -> dict[str, Any]:
    user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
    state = session.get("workflow_state") or PROBLEM_REPORTED
    final = session.get("final_status")
    rows = []
    for s in steps:
        out = s.get("verification_outcome") or "pending"
        rows.append({"title": s.get("title"), "instruction": s.get("instruction"), "outcome": out, "outcome_label": OUTCOME_LABELS.get(out, out),
                     "user_reported_complete": bool(s.get("user_reported_complete")), "visually_verified": bool(s.get("visually_verified")),
                     "note": s.get("verification_note") or "", "simulated": bool(s.get("simulated"))})
    simulated = any(r["simulated"] for r in rows) or any(o.get("simulated") for o in observations)
    status = FINAL_LABELS.get(final) if final else None
    return {
        "device": " ".join(x for x in (session.get("device_name"), session.get("device_model")) if x) or "Not identified",
        "issue": session.get("problem") or (user_msgs[0][:300] if user_msgs else "Not recorded"),
        "initial_symptoms": [m[:200] for m in user_msgs[:3]],
        "observations": [{"text": o["text"], "simulated": bool(o.get("simulated"))} for o in observations][:12],
        "steps": rows,
        "successful": [r["title"] for r in rows if r["outcome"] in ("succeeded", "user_confirmed")],
        "unsuccessful": [r["title"] for r in rows if r["outcome"] == "failed"],
        "verified": [r["title"] for r in rows if r["visually_verified"]],
        "unverified": [r["title"] for r in rows if not r["visually_verified"]],
        "state": state, "status": status or STATUS_LABELS.get(state, state),
        "recommended_next": _NEXT.get(state, _NEXT[ANALYZING]),
        "safety_events": list(session.get("safety_events") or []),
        "simulated": simulated,
    }


def summary_markdown(s: dict[str, Any]) -> str:
    L = ["# Session summary", ""]
    if s["simulated"]:
        L += ["> Contains simulated demo content. It is not real model analysis.", ""]
    L += [f"**Device:** {s['device']}", f"**Issue:** {s['issue']}", f"**Status:** {s['status']}", "", "## Initial symptoms"]
    L += [f"- {x}" for x in s["initial_symptoms"]] or ["- Not recorded"]
    L += ["", "## Observations" + (" (unconfirmed)" if s["observations"] else "")]
    L += [f"- {o['text']}" for o in s["observations"]] or ["- None recorded"]
    L += ["", "## Steps attempted"]
    L += [f"{i}. {r['title']}: {r['outcome_label']}. You reported done: {'yes' if r['user_reported_complete'] else 'no'}; "
          f"visually verified: {'yes' if r['visually_verified'] else 'no'}" for i, r in enumerate(s["steps"], 1)] or ["- None"]
    L += ["", f"**Successful:** {', '.join(s['successful']) or 'none'}", f"**Unsuccessful:** {', '.join(s['unsuccessful']) or 'none'}",
          f"**Visually verified:** {', '.join(s['verified']) or 'none'}", f"**Not verified:** {', '.join(s['unverified']) or 'none'}", ""]
    if s["safety_events"]:
        L += [f"**Safety flags raised:** {', '.join(s['safety_events'])}", ""]
    L += [f"**Recommended next action:** {s['recommended_next']}"]
    return "\n".join(L)

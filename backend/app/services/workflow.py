"""Troubleshooting workflow state machine (pure, no I/O)."""
from __future__ import annotations

PROBLEM_REPORTED = "problem_reported"
INFO = "information_gathering"
AWAIT_IMAGE = "awaiting_visual_evidence"
ANALYZING = "analyzing"
AWAIT_ACTION = "awaiting_user_action"
VERIFYING = "verifying_action"
RESOLVED = "resolved"
ESCALATION = "escalation_required"
COMPLETED = "session_completed"

ACTIVE = (INFO, AWAIT_IMAGE, ANALYZING, AWAIT_ACTION, VERIFYING, RESOLVED, ESCALATION)
STATES = (PROBLEM_REPORTED, *ACTIVE, COMPLETED)

OUTCOME_LABELS = {
    "succeeded": "Worked, visually verified",
    "failed": "Did not work",
    "user_confirmed": "Done, confirmed by you (not visually verified)",
    "user_reported_unverified": "You reported it done, not verified",
    "uncertain": "Result uncertain",
    "pending": "Not yet reported",
    "simulated_not_verified": "Simulated demo, not verified",
}
STATUS_LABELS = {
    PROBLEM_REPORTED: "Problem reported", INFO: "Gathering information", AWAIT_IMAGE: "Waiting for a camera view",
    ANALYZING: "Analysing", AWAIT_ACTION: "Waiting for you to try a step", VERIFYING: "Checking the result of a step",
    RESOLVED: "Resolved", ESCALATION: "Escalation required", COMPLETED: "Session completed",
}


class InvalidTransition(ValueError):
    pass


def can_transition(cur: str, target: str) -> bool:
    if cur not in STATES or target not in STATES:
        return False
    if cur == target:
        return True
    if cur == COMPLETED:
        return target == INFO              # reopening a finished session
    if target == PROBLEM_REPORTED:
        return False                       # initial state only
    return True                            # any active state -> any active state or completed


def transition(cur: str, target: str) -> str:
    if not can_transition(cur, target):
        raise InvalidTransition(f"{cur} -> {target} is not allowed")
    return target


def choose_target(*, first_turn: bool, escalate: bool, resolved: bool, needs_image: bool, new_step: bool,
                  verifying: bool, clarify: bool = False) -> str:
    if escalate:
        return ESCALATION
    if resolved:
        return RESOLVED
    if clarify:
        return INFO
    if needs_image:
        return AWAIT_IMAGE
    if new_step:
        return AWAIT_ACTION
    if verifying:
        return VERIFYING
    return INFO if first_turn else ANALYZING

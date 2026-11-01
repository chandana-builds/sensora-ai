"""Milestone 3 tests. Stdlib-only (no FastAPI/Pydantic/httpx needed): state machine, safety engine, verification,
persistence, recurrence, summary, handoff, privacy, and a full demo scenario."""
import asyncio
import base64
from types import SimpleNamespace as NS

import pytest

from app.ai.base import VisionResult
from app.ai.factory import Providers
from app.ai.demo_provider import DemoTranscriber
from app.services import safety_engine as se
from app.services import workflow as wf
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.engine import apply_turn, decide_verification, normalize
from app.services.handoff import build_handoff, handoff_html, handoff_markdown
from app.services.memory_store import InMemoryMemoryStore
from app.services.recurrence import related_sessions

JPG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 64).decode()
C = "client-demo-0001"


def run(coro):
    return asyncio.run(coro)


# ---------- state machine ----------
def test_transitions():
    assert wf.can_transition(wf.PROBLEM_REPORTED, wf.INFO)
    assert wf.can_transition(wf.AWAIT_ACTION, wf.VERIFYING)
    assert wf.can_transition(wf.ANALYZING, wf.ESCALATION)
    assert wf.can_transition(wf.RESOLVED, wf.COMPLETED)
    assert wf.can_transition(wf.COMPLETED, wf.INFO)               # reopen
    assert not wf.can_transition(wf.COMPLETED, wf.ANALYZING)
    assert not wf.can_transition(wf.ANALYZING, wf.PROBLEM_REPORTED)
    with pytest.raises(wf.InvalidTransition):
        wf.transition(wf.COMPLETED, wf.RESOLVED)


def test_choose_target_priorities():
    base = dict(first_turn=False, escalate=False, resolved=False, needs_image=False, new_step=False, verifying=False)
    assert wf.choose_target(**{**base, "escalate": True, "resolved": True}) == wf.ESCALATION
    assert wf.choose_target(**{**base, "needs_image": True, "new_step": True}) == wf.AWAIT_IMAGE
    assert wf.choose_target(**{**base, "new_step": True}) == wf.AWAIT_ACTION
    assert wf.choose_target(**{**base, "verifying": True}) == wf.VERIFYING
    assert wf.choose_target(**{**base, "first_turn": True}) == wf.INFO
    assert wf.choose_target(**base) == wf.ANALYZING


# ---------- safety engine ----------
@pytest.mark.parametrize("t,cat", [("I can smell gas near the stove", "gas"), ("there is smoke coming out", "fire_smoke"),
    ("I got an electric shock", "electric_shock"), ("it is sparking", "sparks"), ("I see exposed wiring", "exposed_wiring"),
    ("water got into the socket", "water_electrics"), ("my battery is swollen", "swollen_battery"),
    ("the board inside is burnt", "high_voltage_internal"), ("it caught fire", "fire_smoke")])
def test_user_stop(t, cat):
    d = se.classify_user_text(t)
    assert d.action == se.STOP and d.category == cat


@pytest.mark.parametrize("t", ["no smoke or sparks, but it is dead", "I don't smell any gas", "there's no visible smoke", "my wifi is slow"])
def test_user_negation_and_safe(t):
    assert se.classify_user_text(t).action == se.ALLOWED


def test_negation_does_not_hide_real_hazard():
    assert se.classify_user_text("there was no problem until smoke came out").action == se.STOP


@pytest.mark.parametrize("t", ["it is buzzing loudly", "it tripped the breaker", "there is a strange smell", "it is very hot to touch"])
def test_user_clarify(t):
    assert se.classify_user_text(t).action == se.CLARIFY


@pytest.mark.parametrize("t", ["Remove the back cover", "Test the wires with a multimeter", "Replace the capacitor",
    "Reset the circuit breaker", "Check the gas valve", "Unscrew the panel", "Look inside the cooktop"])
def test_instruction_stop(t):
    assert se.classify_instruction(t).action == se.STOP


def test_instruction_allowed_and_clarify():
    assert se.classify_instruction("Unplug the power for 30 seconds").action == se.ALLOWED
    assert se.classify_instruction("Unplug the power for 30 seconds", clarify_pending=True).action == se.CLARIFY
    assert se.classify_instruction("Press the cable firmly into the WAN port").action == se.ALLOWED


def test_never_claims_physical_safety():
    assert se.claims_physical_safety("It looks safe to touch now")
    assert se.claims_physical_safety("The wiring is fine, no danger")
    assert not se.claims_physical_safety("The light is green")
    out = apply_turn(raw={"assistant_message": "The socket looks safe to use now.", "confidence": {"level": "low"}}, session={}, active_step=None,
                     user_reported=False, frames_count=0, vision=None, simulated_mode=False)
    assert se.SAFETY_DISCLAIMER in out["response"]["assistant_message"]


def test_unsafe_model_instruction_overridden_before_delivery():
    out = apply_turn(raw={"assistant_message": "Remove the back cover.", "current_step": {"title": "Open", "instruction": "Unscrew the panel"}},
                     session={}, active_step=None, user_reported=False, frames_count=0, vision=None, simulated_mode=False)
    assert out["overridden"] and out["state"] == wf.ESCALATION and out["new_step"] is None
    assert out["response"]["safety_status"] == "stop" and out["session_updates"]["final_status"] == "escalated"


# ---------- verification ----------
def test_decide_verification_matrix():
    d = lambda **k: decide_verification(**{"verdict": "succeeded", "evidence": "green light visible", "user_reported": True,
                                           "evidence_ok": True, "simulated": False, "mode": "visual", **k})
    assert d() == ("succeeded", "visual", True)
    assert d(evidence_ok=False) == ("user_reported_unverified", "user_report", False)   # user's word alone is never verification
    assert d(evidence="") == ("user_reported_unverified", "user_report", False)
    assert d(simulated=True) == ("simulated_not_verified", "none", False)
    assert d(verdict="uncertain") == ("uncertain", "none", False)
    assert d(verdict="failed")[0] == "failed" and d(verdict="failed")[2] is False
    assert d(mode="user_confirmation", evidence_ok=False) == ("user_confirmed", "user_report", False)
    assert d(verdict="not_applicable", user_reported=False) == ("pending", "none", False)
    assert d(user_reported=False, evidence_ok=False) == ("uncertain", "none", False)


def _active(**k):
    return {"id": "s1", "title": "Restart", "instruction": "Unplug for 30 s.", "expected_result": "internet light is green",
            "verification_mode": "visual", "user_reported_complete": False, **k}


def _turn(raw, *, reported, frames, quality="good", sim_vision=False, sim_mode=False, active=None):
    vis = {"image_quality": quality, "simulated": sim_vision, "observations": ["green light"]} if frames else None
    return apply_turn(raw=raw, session={"workflow_state": wf.AWAIT_ACTION}, active_step=active or _active(), user_reported=reported,
                      frames_count=frames, vision=vis, simulated_mode=sim_mode)


def test_user_says_done_without_evidence_is_not_success():
    raw = {"assistant_message": "Great, next try the cable.", "step_verdict": "succeeded", "step_verdict_evidence": "user said so",
           "current_step": {"title": "Cable", "instruction": "Press the cable in."}}
    o = _turn(raw, reported=True, frames=0)
    assert o["outcome"] == "user_reported_unverified" and o["visually_verified"] is False
    assert o["step_update"]["fields"]["user_reported_complete"] is True and o["step_update"]["fields"]["visually_verified"] is False
    assert o["new_step"] is None and o["response"]["requires_new_image"] and o["state"] == wf.AWAIT_IMAGE   # asks for evidence, no new step


def test_real_visual_evidence_verifies():
    raw = {"assistant_message": "The light is green.", "step_verdict": "succeeded", "step_verdict_evidence": "internet light solid green",
           "issue_resolved": True}
    o = _turn(raw, reported=True, frames=1)
    assert o["outcome"] == "succeeded" and o["visually_verified"] is True
    assert o["state"] == wf.RESOLVED and o["session_updates"]["final_status"] == "resolved_verified"


def test_poor_image_cannot_verify_and_unclear_asks_again():
    raw = {"assistant_message": "Looks ok.", "step_verdict": "succeeded", "step_verdict_evidence": "maybe green"}
    o = _turn(raw, reported=True, frames=1, quality="poor")
    assert o["visually_verified"] is False and o["state"] == wf.AWAIT_IMAGE
    o2 = _turn({"assistant_message": "Can't tell.", "step_verdict": "uncertain"}, reported=False, frames=1)
    assert o2["outcome"] == "uncertain" and o2["response"]["requires_new_image"]


def test_failed_step_moves_to_next_safe_step():
    raw = {"assistant_message": "Still amber.", "step_verdict": "failed", "step_verdict_evidence": "amber light",
           "current_step": {"title": "Cable", "instruction": "Press the WAN cable in."}}
    o = _turn(raw, reported=True, frames=1)
    assert o["outcome"] == "failed" and o["new_step"]["title"] == "Cable" and o["state"] == wf.AWAIT_ACTION


def test_resolved_by_user_word_only_is_flagged_unverified():
    o = _turn({"assistant_message": "Glad it works.", "issue_resolved": True}, reported=False, frames=0)
    assert o["state"] == wf.RESOLVED and o["session_updates"]["final_status"] == "resolved_unverified"
    assert "haven't been able to verify" in o["response"]["assistant_message"]


def test_one_instruction_at_a_time_when_step_pending():
    raw = {"assistant_message": "Try this.", "current_step": {"title": "Other", "instruction": "Do another thing."}}
    o = _turn(raw, reported=False, frames=0)
    assert o["new_step"] is None and "finish the current step" in o["response"]["assistant_message"]


def test_normalize_rejects_garbage_and_enforces_stop_invariant():
    with pytest.raises(ValueError):
        normalize({"nope": 1})
    r = normalize({"assistant_message": "x", "safety_status": "stop", "current_step": {"title": "a", "instruction": "b"}})
    assert r["current_step"] is None and r["requested_user_action"] is None


# ---------- orchestrator, persistence, privacy ----------
class FakeReasoner:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    async def reason(self, **kw):
        self.calls.append(kw)
        return self.replies.pop(0)


class FakeVision:
    async def analyze(self, frames, *, context):
        return VisionResult(observations=["internet light solid green"], provider="fake", image_quality="good")


def real_orch(replies, store=None):
    store = store or InMemoryMemoryStore()
    store.create_session(C, "s1", evidence_consent=False)
    r = FakeReasoner(replies)
    return AgentOrchestrator(store, Providers(DemoTranscriber(), FakeVision(), r, "real")), store, r


def test_hazard_stops_before_model_is_called():
    o, store, r = real_orch([])
    out = run(o.handle_turn(C, "s1", NS(text="I can smell gas from the stove", frames=[], input_mode="text", user_level=None, reported_step_done=False)))
    assert out["workflow_state"] == wf.ESCALATION and r.calls == [] and out["response"]["safety_status"] == "stop"
    assert store.get_session(C, "s1")["safety_events"] == ["gas"] and store.get_session(C, "s1")["final_status"] == "escalated"


def test_clarification_flow_then_continues():
    o, store, r = real_orch([{"assistant_message": "Thanks. Which router model is it?", "confidence": {"level": "low"}}])
    out = run(o.handle_turn(C, "s1", NS(text="there is a strange smell from my router", frames=[], input_mode="text", user_level=None, reported_step_done=False)))
    assert out["response"]["assistant_message"] == se.CLARIFY_QUESTION and r.calls == [] and store.get_session(C, "s1")["clarify_pending"]
    out2 = run(o.handle_turn(C, "s1", NS(text="No smoke, no sparks, it's not hot. Just the smell of new plastic.", frames=[], input_mode="text", user_level=None, reported_step_done=False)))
    assert len(r.calls) == 1 and not store.get_session(C, "s1")["clarify_pending"] and out2["response"]["safety_status"] == "ok"


def test_real_mode_verification_persists_both_flags_separately():
    first = {"assistant_message": "Restart it.", "current_step": {"title": "Restart", "instruction": "Unplug for 30 seconds.",
             "expected_result": "internet light green"}, "device": {"type": "router", "model": "TP-Link X20"}}
    second = {"assistant_message": "The light is green.", "step_verdict": "succeeded", "step_verdict_evidence": "internet light solid green", "issue_resolved": True}
    o, store, r = real_orch([first, second])
    run(o.handle_turn(C, "s1", NS(text="my wifi has no internet", frames=[], input_mode="text", user_level="beginner", reported_step_done=False)))
    s = store.list_steps(C, "s1")[0]
    assert s["user_reported_complete"] is False and s["visually_verified"] is False
    assert store.get_session(C, "s1")["device_model"] == "TP-Link X20" and store.get_session(C, "s1")["user_level"] == "beginner"
    assert r.calls[0]["context"]["user_level"] == "beginner"
    out = run(o.handle_turn(C, "s1", NS(text="Done, here it is", frames=[JPG], input_mode="text", user_level=None, reported_step_done=True)))
    s = store.list_steps(C, "s1")[0]
    assert s["user_reported_complete"] and s["visually_verified"] and s["verification_outcome"] == "succeeded"
    assert out["workflow_state"] == wf.RESOLVED and store.get_session(C, "s1")["final_status"] == "resolved_verified"
    assert r.calls[1]["context"]["active_step"]["title"] == "Restart"


def test_evidence_only_stored_with_consent_and_erased_on_delete():
    o, store, _ = real_orch([{"assistant_message": "ok"}, {"assistant_message": "ok2"}])
    run(o.handle_turn(C, "s1", NS(text="hello router", frames=[JPG], input_mode="text", user_level=None, reported_step_done=False)))
    assert store.list_evidence(C, "s1") == []                      # no consent -> nothing retained
    store.update_session(C, "s1", evidence_consent=True)
    run(o.handle_turn(C, "s1", NS(text="again", frames=[JPG], input_mode="text", user_level=None, reported_step_done=False)))
    ev = store.list_evidence(C, "s1")
    assert len(ev) == 1 and "data" not in ev[0] and ev[0]["expires_at"]
    assert store.delete_evidence(C, "s1") == 1 and store.list_evidence(C, "s1") == []


def test_experience_preference_saved_only_with_consent():
    s = InMemoryMemoryStore()
    assert s.set_experience_level(C, "beginner", remember=False)["user_level"] is None
    assert s.set_experience_level(C, "beginner", remember=True)["user_level"] == "beginner"
    assert s.set_experience_level(C, "beginner", remember=False)["user_level"] is None   # withdrawing consent erases it


def test_saved_level_is_used_in_new_session():
    o, store, r = real_orch([{"assistant_message": "hi"}])
    store.set_experience_level(C, "experienced", True)
    run(o.handle_turn(C, "s1", NS(text="my dishwasher will not drain", frames=[], input_mode="text", user_level=None, reported_step_done=False)))
    assert r.calls[0]["context"]["user_level"] == "experienced"


def test_cross_client_isolation():
    o, store, _ = real_orch([])
    with pytest.raises(Exception):
        run(o.handle_turn("someone-else-1234", "s1", NS(text="hi", frames=[], input_mode="text", user_level=None, reported_step_done=False)))


# ---------- full scenario, recurrence, summary, handoff ----------
def scenario():
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
    import run_demo_scenario as s
    return run(s.main(verbose=False))


def test_full_demo_scenario_ends_in_escalation_and_never_verifies():
    store, o, out, rel = scenario()
    assert [r["workflow_state"] for r in out] == [wf.AWAIT_IMAGE, wf.AWAIT_ACTION, wf.AWAIT_ACTION, wf.AWAIT_ACTION, wf.ESCALATION]
    assert all(r["simulated"] for r in out) and all(r["response"]["assistant_message"].startswith("[Simulated demo]") for r in out)
    steps = store.list_steps(C, "s1")
    assert [s["verification_outcome"] for s in steps] == ["simulated_not_verified", "failed", "failed"]
    assert all(s["user_reported_complete"] and not s["visually_verified"] for s in steps)
    sess = store.get_session(C, "s1")
    assert sess["workflow_state"] == wf.COMPLETED and sess["final_status"] == "escalated" and sess["summary"]["simulated"]
    assert len(store.list_messages(C, "s1", 100)) == 10 and store.list_observations(C, "s1")


def test_recurring_issue_retrieval():
    store, o, out, rel = scenario()
    assert rel and rel[0]["id"] == "s1" and [s["outcome"] for s in rel[0]["steps"]] == ["simulated_not_verified", "failed", "failed"]
    assert related_sessions({"id": "x", "device_name": "dishwasher", "problem": "not draining"}, store.list_sessions(C)) == []


def test_recurrence_context_reaches_model_without_assuming_old_diagnosis():
    store, o, out, rel = scenario()
    store.create_session(C, "s3")
    r = FakeReasoner([{"assistant_message": "Last time you tried a restart. What do the lights show now?"}])
    o2 = AgentOrchestrator(store, Providers(DemoTranscriber(), FakeVision(), r, "real"))
    run(o2.handle_turn(C, "s3", NS(text="my router internet is not working again, orange light", frames=[], input_mode="text", user_level=None, reported_step_done=False)))
    block = r.calls[0]["context"]["prior_history"]
    assert "Restart router" in block and "not current facts" in block and "Do not assume the earlier diagnosis" in block


def test_summary_and_handoff_content_and_consent():
    store, o, out, rel = scenario()
    sm = o.summary(C, "s1")
    assert sm["status"].startswith("Escalated") and sm["unsuccessful"] == ["Restart router", "Check WAN cable"] and sm["verified"] == []
    assert "Check power" in sm["unverified"] and sm["device"].startswith("Wi-Fi router") and sm["recommended_next"]
    h = o.handoff(C, "s1", "remote_expert", include_evidence=True)
    assert h["pathway_label"] == "Remote human expert" and h["evidence_included"] is False          # no consent -> no evidence
    assert all(c["status"] == "Unconfirmed" for c in h["possible_causes"]) and h["possible_causes"]
    assert h["unresolved_questions"] and any("No technician" in d for d in h["disclaimers"]) and h["transcript"]
    md = handoff_markdown(h)
    assert "UNCONFIRMED" in md and "has been contacted or booked" in md and "<script>" not in handoff_html(h)
    with pytest.raises(PermissionError):
        o.export(C, "s1", pathway="local_technician", include_evidence=False, consent_to_share=False, fmt="md")
    content, mime, name = o.export(C, "s1", pathway="local_technician", include_evidence=False, consent_to_share=True, fmt="html")
    assert mime.startswith("text/html") and name.endswith(".html") and "Technician handoff" in content


def test_handoff_includes_evidence_references_only_with_consent():
    store, o, out, rel = scenario()
    store.update_session(C, "s1", evidence_consent=True)
    store.save_evidence(C, "s1", b"\xff\xd8\xff", "frame", 30)
    h = o.handoff(C, "s1", "local_technician", include_evidence=True)
    assert h["evidence_included"] and len(h["evidence_references"]) == 1
    assert not o.handoff(C, "s1", "local_technician", include_evidence=False)["evidence_references"]


def test_reopen_completed_session_resumes():
    store, o, out, rel = scenario()
    r = FakeReasoner([{"assistant_message": "Let's look again. What do the lights show?"}])
    o2 = AgentOrchestrator(store, Providers(DemoTranscriber(), FakeVision(), r, "real"))
    out = run(o2.handle_turn(C, "s1", NS(text="it has started again", frames=[], input_mode="text", user_level=None, reported_step_done=False)))
    assert out["workflow_state"] in (wf.ANALYZING, wf.INFO) and store.get_session(C, "s1")["final_status"] is None

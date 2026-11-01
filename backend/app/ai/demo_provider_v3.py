"""Demo reasoner for Milestone 3: M2 scripts plus verdict/device fields. Always simulated, so it can
never produce visually_verified=True (the engine enforces this)."""
from __future__ import annotations

from typing import Any

from .config import AISettings
from .demo_provider import DemoReasoner, DemoTranscriber, DemoVision

_VERDICT = {"router": {3: "succeeded", 4: "failed", 5: "failed"}, "induction": {3: "succeeded", 4: "failed"}}
_DEVICE = {"router": {"type": "Wi-Fi router", "model": None}, "induction": {"type": "Induction cooktop", "model": None}}
_USER_CONFIRM = {"Check cookware"}


class DemoReasonerV3(DemoReasoner):
    def __init__(self, scenario: str) -> None:
        super().__init__(scenario)
        self.scenario = scenario if scenario in _VERDICT else "router"

    async def reason(self, *, system, history, user_text, vision, context) -> dict[str, Any]:
        out = await super().reason(system=system, history=history, user_text=user_text, vision=vision, context=context)
        n = int(context.get("user_turn_index", 1))
        out["step_verdict"] = _VERDICT[self.scenario].get(n, "not_applicable") if context.get("active_step") else "not_applicable"
        out["step_verdict_evidence"] = "[Simulated] scripted verdict, no real image analysis." if out["step_verdict"] != "not_applicable" else ""
        if n >= 2:
            out["device"] = _DEVICE[self.scenario]
        if out.get("current_step"):
            out["current_step"]["verification_mode"] = "user_confirmation" if out["current_step"]["title"] in _USER_CONFIRM else "visual"
        return out


def build_providers_v3(s: AISettings) -> Any:
    from .factory import Providers, build_providers
    p = build_providers(s)
    if p.mode == "demo":
        return Providers(DemoTranscriber(), DemoVision(s.demo_scenario), DemoReasonerV3(s.demo_scenario), "demo")
    return p

"""Deterministic DEMO provider. Never presented as real model output.

Vision output is canned (it does NOT look at the image). Transcription is unavailable in
demo mode rather than faked: type your messages instead.
"""
from __future__ import annotations

from typing import Any, Sequence

from .base import ProviderError, TranscriptionResult, VisionResult

TAG = "[Simulated demo] "

SCENARIOS: dict[str, dict[str, Any]] = {
    "router": {
        "title": "Wi-Fi router: no internet",
        "vision": ["Simulated: a router with several indicator lights is in view.",
                   "Simulated: the internet/WAN light appears amber, not green."],
        "turns": [
            {"say": "Thanks. Which router is it, and are you a beginner or experienced with networking? "
                    "If you can, show me the front lights.",
             "requires_new_image": True, "confidence": ("low", "Nothing seen yet."), "causes": []},
            {"say": "The internet light looks amber, which often means no connection from your provider. "
                    "First check the power adapter.",
             "step": ("Check power", "Make sure the power adapter is pushed fully into the router and the wall socket.",
                      "The power light stays solid."),
             "verification": True, "confidence": ("medium", "Based on one amber light."),
             "causes": [("Temporary provider or line issue", "medium"), ("Loose cable", "low")]},
            {"say": "Good. Now restart it: unplug the power, wait 30 seconds, plug it back in, then show me the lights after two minutes.",
             "step": ("Restart router", "Unplug power for 30 seconds, plug it back in and wait two minutes.",
                      "Lights cycle and the internet light turns green."),
             "verification": True, "confidence": ("medium", "Restart fixes most temporary faults."),
             "causes": [("Temporary glitch", "medium")]},
            {"say": "Still amber. Check the thin cable in the router's WAN or internet port is clicked in firmly at both ends.",
             "step": ("Check WAN cable", "Press the WAN cable firmly into the router port and the wall or modem end.",
                      "A click, then the internet light changes."),
             "verification": True, "confidence": ("medium", "Cable seating is the next safe external check."),
             "causes": [("Loose WAN cable", "medium"), ("Provider outage", "medium")]},
            {"say": "The safe checks are done and the problem remains. I recommend contacting your internet provider and sharing this session summary.",
             "escalate": True, "confidence": ("medium", "Likely outside your home."),
             "causes": [("Provider outage or line fault", "medium")]},
        ],
    },
    "induction": {
        "title": "Induction stove: not heating",
        "vision": ["Simulated: an induction cooktop with a lit display is in view.",
                   "Simulated: a pan sits on a zone."],
        "turns": [
            {"say": "Thanks. What is the model, are you a beginner or experienced, and what does the display show? Show me the control panel if you can.",
             "requires_new_image": True, "confidence": ("low", "Nothing seen yet."), "causes": []},
            {"say": "Induction needs magnetic cookware. First, check that your pan is induction-compatible and centred on the zone.",
             "step": ("Check cookware", "Hold a fridge magnet to the pan base; it should stick. Centre the pan on the ring.",
                      "The zone starts heating."),
             "verification": True, "confidence": ("medium", "Cookware is the most common cause."),
             "causes": [("Non-magnetic or off-centre pan", "medium"), ("Safety lock on", "low")]},
            {"say": "Next, check whether the child lock is on. Look for a key symbol on the panel and use your manual's unlock method.",
             "step": ("Check child lock", "Look for a lock symbol and follow the unlock steps in your user manual.",
                      "The lock symbol turns off."),
             "verification": True, "confidence": ("medium", "A common cause of no response."),
             "causes": [("Child lock enabled", "medium")]},
            {"say": "If an error code stays on the display, don't open the stove. Note the code and contact the manufacturer's service.",
             "escalate": True, "confidence": ("medium", "Persistent faults need a technician."),
             "causes": [("Internal fault needing service", "medium")]},
        ],
    },
}


class DemoTranscriber:
    name = "demo"

    async def transcribe(self, wav: bytes, *, language_bias: Sequence[str] | None = None) -> TranscriptionResult:
        raise ProviderError("Voice transcription isn't available in demo mode. Please type your message.",
                            code="demo_no_stt", status=503)


class DemoVision:
    name = "demo"

    def __init__(self, scenario: str) -> None:
        self.s = SCENARIOS.get(scenario, SCENARIOS["router"])

    async def analyze(self, frames: Sequence[bytes], *, context: str) -> VisionResult:
        return VisionResult(observations=list(self.s["vision"]), provider=self.name, simulated=True)


class DemoReasoner:
    name = "demo"

    def __init__(self, scenario: str) -> None:
        self.s = SCENARIOS.get(scenario, SCENARIOS["router"])

    async def reason(self, *, system, history, user_text, vision, context) -> dict[str, Any]:
        turns = self.s["turns"]
        idx = min(max(int(context.get("user_turn_index", 1)) - 1, 0), len(turns) - 1)
        t = turns[idx]
        level, note = t["confidence"]
        step = t.get("step")
        return {
            "assistant_message": TAG + t["say"],
            "observations": [TAG + o for o in (vision.observations if vision else [])],
            "likely_causes": [{"cause": c, "likelihood": l} for c, l in t["causes"]],
            "confidence": {"level": level, "note": note},
            "current_step": {"title": step[0], "instruction": step[1], "expected_result": step[2]} if step else None,
            "requested_user_action": step[1] if step else None,
            "requires_new_image": bool(t.get("requires_new_image")),
            "verification_required": bool(t.get("verification")),
            "safety_status": "ok",
            "escalation_recommended": bool(t.get("escalate")),
        }

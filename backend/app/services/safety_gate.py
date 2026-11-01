"""Safety gate applied to user input AND to every model instruction.

Keyword/regex based: it ignores negation and errs toward false alarms. It must be merged
with the Milestone 1 safety.py rules (single source of truth) when wiring.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..schemas_ai import TroubleshootingResponse

_HAZARD = {
    "gas": re.compile(r"\bgas (leak|smell)|smell(s|ing)? (of )?gas|\bsmells? like gas|\blpg\b.*\bleak", re.I),
    "fire/smoke": re.compile(r"\bsmok(e|ing)\b|\bburning (smell|plastic)|\bsmell(s|ing)? (of )?burn|\bcaught fire|\bon fire|\bflames?\b", re.I),
    "sparks": re.compile(r"\bspark(s|ing|ed)?\b|\barc(ing)?\b", re.I),
    "electric shock": re.compile(r"\b(electric(al)? )?shock(ed)?\b|\bgot zapped|\btingl(e|ing) when (i )?touch", re.I),
    "exposed wiring": re.compile(r"\bexposed (wire|wiring|cable)|\bbare wire|\bfrayed (wire|cord|cable)|\bmelted (wire|cord|plug)", re.I),
    "water near power": re.compile(r"\b(water|wet|liquid)\b.{0,40}\b(socket|outlet|plug|power|inside)\b|\b(socket|outlet|plug)\b.{0,40}\b(water|wet)\b", re.I),
    "swollen battery": re.compile(r"\b(swollen|bulging|puffed|ballooned) battery|\bbattery (is )?(swollen|bulging|hot|leaking)", re.I),
}

_UNSAFE_INSTRUCTION = re.compile(
    r"\b(open|remove|take off|unscrew|pry|detach)\b.{0,30}\b(back|cover|panel|casing|housing|lid|enclosure|plate)\b"
    r"|\bunscrew\b|\bdisassembl|\btake (it|the \w+) apart\b"
    r"|\b(touch|handle|cut|strip|splice|bypass|short|jump(er)?)\b.{0,25}\b(wire|wiring|cable ends?|terminals?|live)\b"
    r"|\bmultimeter\b|\bsolder|\b(replace|swap)\b.{0,25}\b(capacitor|fuse|board|heating element|coil|transformer|igbt)\b"
    r"|\bgas (valve|line|pipe|regulator|knob)\b|\bpilot light\b|\blight (a|the) (match|lighter)"
    r"|\b(plug|switch on)\b.{0,25}\bwet\b|\binside (the )?(device|unit|cooktop|router|appliance)\b",
    re.I)

STOP_MESSAGES = {
    "gas": "Please stop and move away from the device right now. Do not use switches, flames or phones near it. "
           "Get to fresh air and call your gas supplier's emergency line or your local emergency number.",
    "default": "Please stop here. This could be unsafe, and I can't guide you through it. "
               "Don't touch the device or its wiring. If it is safe to reach, switch off the power at the wall, "
               "then contact a qualified technician or your local emergency number if there's smoke, fire or a shock risk.",
}


def assess_user_text(text: str) -> tuple[bool, str | None]:
    """Return (is_hazard, hazard_label)."""
    for label, rx in _HAZARD.items():
        if rx.search(text):
            return True, label
    return False, None


def violates_instruction_policy(text: str) -> bool:
    t = text or ""
    for m in _UNSAFE_INSTRUCTION.finditer(t):
        prefix = t[max(0, m.start() - 40): m.start()]
        if not re.search(r"\b(do not|don'?t|never|not to|avoid|without)\b", prefix, re.I):
            return True
    return False


def stop_response(label: str | None) -> "TroubleshootingResponse":
    from ..schemas_ai import Confidence, SafetyStatus, TroubleshootingResponse
    msg = STOP_MESSAGES["gas"] if label == "gas" else STOP_MESSAGES["default"]
    return TroubleshootingResponse(
        assistant_message=msg, confidence=Confidence(level="high", note="Safety rule triggered."),
        safety_status=SafetyStatus.stop, escalation_recommended=True)


def screen_response(resp: "TroubleshootingResponse") -> tuple["TroubleshootingResponse", bool]:
    """Block unsafe model instructions. Returns (response, overridden)."""
    parts = [resp.assistant_message, resp.requested_user_action or ""]
    if resp.current_step:
        parts += [resp.current_step.title, resp.current_step.instruction]
    if violates_instruction_policy(" ".join(parts)):
        return stop_response(None), True
    return resp, False

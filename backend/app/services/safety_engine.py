"""Standalone safety policy engine (Milestone 3).

Applied in code BEFORE any instruction reaches the user, in two places:
  classify_user_text()  - what the user reports (hazards stop the flow before the model is consulted)
  classify_instruction() - what the model wants the user to do

Results: allowed | clarification_required | stop_and_escalate.
Keyword/regex based: negation is handled only for the immediate "no/not/without X" form; otherwise it
errs toward false alarms. It never states that anything is physically safe.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ALLOWED, CLARIFY, STOP = "allowed", "clarification_required", "stop_and_escalate"


@dataclass(frozen=True)
class Decision:
    action: str
    category: str | None = None
    reason: str = ""

    @property
    def blocked(self) -> bool:
        return self.action != ALLOWED


_NEG = re.compile(
    r"\b(no|not|without|never|nothing|isn'?t|aren'?t|doesn'?t|don'?t|didn'?t|hasn'?t|haven'?t)\s+"
    r"(?:(?:see|notice|smell|hear|spot|get|feel|seen|any|visible|a|an|the|signs?\s+of|sign\s+of)\s+)*"
    r"(?:\w+\s+(?:or|and|nor)\s+)*$", re.I)

_STOP_USER = {
    "gas": r"\bgas (leak|smell)|smell(s|ing)? (of )?gas|\bsmells? like gas|\blpg\b.{0,20}\bleak",
    "fire_smoke": r"\bsmok(e|ing)\b|\bburning (smell|plastic|rubber)|\bsmell(s|ing)? (of )?burn|\bburnt smell|\bcaught fire|\bon fire\b|\bflames?\b",
    "sparks": r"\bspark(s|ing|ed)?\b|\barcing\b",
    "electric_shock": r"\b(electric(al)? )?shock(ed)?\b|\bgot zapped|\btingl(e|ing) when (i )?touch",
    "exposed_wiring": r"\bexposed (wire|wiring|cable)|\bbare wire|\bfrayed (wire|cord|cable)|\bmelted (wire|cord|plug|socket)",
    "water_electrics": r"\b(water|wet|liquid|spill\w*)\b.{0,40}\b(socket|outlet|plug|power|inside|internal)\b|\b(socket|outlet|plug)\b.{0,40}\b(water|wet|damp)\b",
    "swollen_battery": r"\b(swollen|bulging|puffed|ballooned) battery|\bbattery (is )?(swollen|bulging|leaking|very hot)",
    "high_voltage_internal": r"\bhigh[- ]voltage\b|\b(inside|internal)\b.{0,40}\b(burnt|burned|melted|scorched|damaged|fault)|"
                             r"\b(burnt|burned|scorched|melted)\b.{0,30}\b(board|pcb|component|capacitor|transformer|coil)\b|"
                             r"\bcapacitor\b.{0,20}\b(bulg\w*|leak\w*|burst|blown)\b",
}
_CLARIFY_USER = (r"\b(buzz(ing)?|hum(ming)?|crackl(e|ing)|hiss(ing)?)\b|\b(very |too |extremely )?hot to (the )?touch\b|"
                 r"\boverheat(ing|ed)?\b|\b(trips?|tripped|tripping)\b.{0,25}\b(breaker|mcb|fuse|switch)\b|"
                 r"\b(strange|weird|odd|funny|unusual)\b.{0,10}\b(smell|noise|sound)\b|\bsmells?\b")

_UNSAFE_INSTRUCTION = re.compile(
    r"\b(open|remove|take off|unscrew|pry|detach|lift off)\b.{0,30}\b(back|cover|panel|casing|housing|lid|enclosure|plate)\b"
    r"|\bunscrew\b|\bdisassembl|\btake (it|the \w+) apart\b"
    r"|\b(touch|handle|cut|strip|splice|bypass|short|jump(er)?)\b.{0,25}\b(wire|wiring|cable ends?|terminals?|live)\b"
    r"|\bmultimeter\b|\bsolder|\b(replace|swap|repair)\b.{0,25}\b(capacitor|fuse|board|heating element|coil|transformer|igbt|element|motor)\b"
    r"|\bgas (valve|line|pipe|regulator|knob|cylinder)\b|\bpilot light\b|\blight (a|the) (match|lighter)"
    r"|\b(plug|switch on|turn on|power on)\b.{0,25}\b(wet|damp|soaked)\b|\binside (of )?(the )?(device|unit|cooktop|stove|router|appliance|machine)\b"
    r"|\b(reset|flip|switch)\b.{0,20}\b(circuit )?(breaker|mcb|fuse box|distribution board|mains)\b|\bwiring\b.{0,20}\b(check|inspect|test)\b", re.I)
_POWER_ACTION = re.compile(r"\b(unplug|plug (it )?(back )?in|switch (it )?(on|off)|power (cycle|off|on)|turn (it )?(on|off))\b", re.I)
_SAFETY_CLAIM = re.compile(
    r"\b(it|this|that|everything|the (device|unit|stove|router|cooktop|wiring|socket))('s| is| looks| seems| appears)?\b.{0,18}"
    r"\b(safe|not dangerous|harmless|fine to touch|no danger)\b|\bsafe to (touch|use|plug|handle|operate|turn on|switch on)\b"
    r"|\bno (visible )?(risk|danger|hazard)\b|\blooks (safe|fine to (use|touch))\b", re.I)

SAFETY_DISCLAIMER = ("I can't judge whether anything is physically safe from a camera image, "
                     "so please use your own judgement and stop if anything seems wrong.")
CLARIFY_QUESTION = ("Before we go on, a quick safety check: is there any smoke, burning smell, sparks, a very hot "
                    "casing, or liquid near the device or its socket? If yes, please stop and keep clear. If not, tell me and we'll continue.")

_STOP_TEXT = {
    "gas": "Please stop and move away right now. Don't use switches, flames or phones near it. Get to fresh air and call your gas supplier's emergency line or your local emergency number.",
    "fire_smoke": "Please stop using it. If it is safe to reach without touching the device, switch it off at the wall, then move away. If there is smoke or fire, leave and call your local emergency number.",
    "electric_shock": "Please don't touch the device again. If you can do it without touching it, switch off the supply at the wall or main switch. Have a qualified electrician check it before any further use.",
    "exposed_wiring": "Please don't touch the device or the wiring, and keep others away. A qualified electrician must look at this before it is used again.",
    "water_electrics": "Please don't touch the device or the socket. If you can reach the main switch safely and dry, turn it off. A qualified electrician or the manufacturer's service should check it before use.",
}
_STOP_DEFAULT = ("Please stop here. This could be unsafe, and I can't guide you through it. Don't open the device or touch its wiring. "
                 "If it is safe to reach, switch it off at the wall, then contact a qualified technician or the manufacturer's service.")


def stop_message(category: str | None) -> str:
    return _STOP_TEXT.get(category or "", _STOP_DEFAULT)


def _hits(patterns: dict[str, str] | str, text: str):
    items = patterns.items() if isinstance(patterns, dict) else [("clarify", patterns)]
    for label, rx in items:
        for m in re.finditer(rx, text, re.I):
            if not _NEG.search(text[max(0, m.start() - 40): m.start()]):
                return label
    return None


def classify_user_text(text: str) -> Decision:
    t = text or ""
    label = _hits(_STOP_USER, t)
    if label:
        return Decision(STOP, label, f"User reported a {label.replace('_', ' ')} signal.")
    if _hits(_CLARIFY_USER, t):
        return Decision(CLARIFY, "ambiguous_signal", "User mentioned a symptom that needs a safety check.")
    return Decision(ALLOWED)


def classify_instruction(text: str, *, clarify_pending: bool = False) -> Decision:
    t = text or ""
    for m in _UNSAFE_INSTRUCTION.finditer(t):
        prefix = t[max(0, m.start() - 40): m.start()]
        if not re.search(r"\b(do not|don'?t|never|not to|avoid|without)\b", prefix, re.I):
            return Decision(STOP, "unsafe_instruction", "Instruction involves internal/electrical/gas work.")
    if clarify_pending and _POWER_ACTION.search(t):
        return Decision(CLARIFY, "unanswered_safety_check", "Power action requested while a safety check is unanswered.")
    return Decision(ALLOWED)


def claims_physical_safety(text: str) -> bool:
    return bool(_SAFETY_CLAIM.search(text or ""))

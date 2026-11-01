"""Safety policy engine (pure Python, no third-party imports).

Rule-based and deliberately conservative: it prefers false positives to missed
hazards. It does not understand negation ("no smell of gas" is still flagged).
It is a first line of defence; the AI layer (Milestone 2) must add its own
judgement and must pass every instruction through `screen_instruction`.
"""
import re
from dataclasses import dataclass, field
from enum import Enum


class SafetyLevel(str, Enum):
    OK = "ok"
    CAUTION = "caution"
    STOP = "stop"


_ORDER = {SafetyLevel.OK: 0, SafetyLevel.CAUTION: 1, SafetyLevel.STOP: 2}
_FLAGS = re.I | re.S


@dataclass(frozen=True)
class Rule:
    category: str
    level: SafetyLevel
    pattern: re.Pattern
    guidance: str


def _rule(category: str, level: SafetyLevel, pattern: str, guidance: str) -> Rule:
    return Rule(category, level, re.compile(pattern, _FLAGS), guidance)


RULES: tuple[Rule, ...] = (
    _rule(
        "gas_leak", SafetyLevel.STOP,
        r"\b(smell\w*|smelt|odou?r|hiss\w*|leak\w*)\b.{0,25}\b(gas|lpg|propane|methane)\b"
        r"|\b(gas|lpg|propane|methane)\b.{0,25}\b(smell\w*|odou?r|hiss\w*|leak\w*)\b",
        "Possible gas leak. Do not touch switches, flames or electronics. Open windows if "
        "it is safe, leave the area, and call your gas provider or emergency services from outside.",
    ),
    _rule(
        "fire_or_smoke", SafetyLevel.STOP,
        r"\b(smoke(?!\s*(detector|alarm))|smoking|fire(?!\s*(tv|stick|tablet|hd|os|phone))"
        r"|flames?|sparks?|sparking|arcing|burning smell|burnt smell"
        r"|smells? (like )?(something )?burn\w*)\b",
        "Possible fire or burning hazard. Disconnect power only if you can do so safely, move "
        "away from the device, and contact emergency services if there is fire or heavy smoke.",
    ),
    _rule(
        "electric_shock", SafetyLevel.STOP,
        r"\b(electric(al)? shock|shocked me|got shocked|tingl\w* (when|if) (i )?touch\w*)\b",
        "Electric shock risk. Do not touch the device. Switch off power at the main breaker if "
        "it is safe, and ask a qualified electrician to inspect it.",
    ),
    _rule(
        "exposed_wiring", SafetyLevel.STOP,
        r"\b(exposed|bare|frayed|damaged|melted|cracked)\b.{0,15}\b(wire|wires|wiring|cable|cord|insulation)\b",
        "Damaged or exposed wiring. Do not touch it or try to repair it. Unplug only if the "
        "plug and cord are dry and undamaged, and call a qualified electrician.",
    ),
    _rule(
        "water_and_electricity", SafetyLevel.STOP,
        r"\b(water|liquid|flood\w*|wet)\b.{0,40}\b(outlet|socket|plug|power strip|wiring|breaker)\b"
        r"|\b(outlet|socket|plug|power strip|breaker)\b.{0,40}\b(wet|water|flood\w*)\b",
        "Water near electrical parts. Stay away, do not touch the device or outlet, switch off "
        "power at the breaker only if you can reach it dry, and call an electrician.",
    ),
    _rule(
        "damaged_battery", SafetyLevel.STOP,
        r"\b(swollen|bulging|puffed|ballooned|swelling)\b.{0,20}\b(battery|lithium|power ?bank)\b"
        r"|\b(battery|power ?bank)\b.{0,25}\b(swollen|bulging|puffed|swelling|leaking|very hot)\b",
        "Damaged lithium battery. Stop using and charging the device, keep it on a non-flammable "
        "surface away from anything combustible, and contact the manufacturer or a recycling centre.",
    ),
    _rule(
        "opening_appliance", SafetyLevel.CAUTION,
        r"\b(open\w*|take apart|taking apart|remov\w* the (back|cover|panel|casing)|unscrew\w*)\b.{0,30}"
        r"\b(microwave|power supply|psu|tv|television|appliance|fridge|refrigerator|oven|"
        r"washing machine|geyser|water heater|inverter|ups|stove|cooktop)\b",
        "Do not open mains-powered appliances. Internal parts can hold dangerous voltage even "
        "when unplugged. Describe what you see from the outside and consider a technician.",
    ),
    _rule(
        "overheating", SafetyLevel.CAUTION,
        r"\b(overheat\w*|too hot to touch|very hot|extremely hot)\b",
        "Overheating can be a hazard. Switch the device off and let it cool in an open area "
        "before doing anything else.",
    ),
)


@dataclass
class SafetyAssessment:
    level: SafetyLevel = SafetyLevel.OK
    categories: list[str] = field(default_factory=list)
    guidance: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"level": self.level.value, "categories": self.categories, "guidance": self.guidance}


def assess_text(text: str) -> SafetyAssessment:
    """Assess free text from the user (problem description or a chat message)."""
    result = SafetyAssessment()
    for rule in RULES:
        if rule.pattern.search(text or ""):
            result.categories.append(rule.category)
            result.guidance.append(rule.guidance)
            if _ORDER[rule.level] > _ORDER[result.level]:
                result.level = rule.level
    return result


def max_level(*levels: str) -> str:
    best = SafetyLevel.OK
    for lv in levels:
        cand = SafetyLevel(lv)
        if _ORDER[cand] > _ORDER[best]:
            best = cand
    return best.value


@dataclass(frozen=True)
class InstructionCheck:
    allowed: bool
    reason: str | None = None


_DANGEROUS_INSTRUCTIONS: tuple[tuple[re.Pattern, str], ...] = tuple(
    (re.compile(p, _FLAGS), r)
    for p, r in (
        (r"\b(open|remove|take off|unscrew|pry)\b.{0,40}\b(back|cover|casing|panel|housing|enclosure)\b",
         "Instruction asks the user to open a device."),
        (r"\b(touch|hold|cut|strip|splice|reconnect|bridge|short)\b.{0,30}\b(wire|wires|wiring|terminal|terminals|live|mains)\b",
         "Instruction involves handling wiring or live parts."),
        (r"\bgas\b.{0,20}\b(valve|line|pipe|cylinder|regulator|connection)\b",
         "Instruction involves gas components."),
        (r"\b(bypass|jumper|disable)\b.{0,25}\b(fuse|breaker|safety|interlock|thermostat)\b",
         "Instruction defeats a safety device."),
        (r"\b(puncture|pierce|crush)\b.{0,20}\bbattery\b",
         "Instruction damages a battery."),
    )
)


def screen_instruction(text: str) -> InstructionCheck:
    """Gate for any troubleshooting instruction BEFORE it is shown to a user."""
    for pattern, reason in _DANGEROUS_INSTRUCTIONS:
        if pattern.search(text or ""):
            return InstructionCheck(False, reason)
    return InstructionCheck(True)

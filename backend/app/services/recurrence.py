"""Find earlier sessions about the same device/problem and summarise what was already tried."""
from __future__ import annotations

import re
from typing import Any

from .workflow import OUTCOME_LABELS

_STOP = set("the a an is are was were it its my our i me we you to of and or in on at for with not no this that my has have had "
            "wont won't doesnt doesn't dont don't cant can't keep keeps again still working work works issue problem".split())


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2 and w not in _STOP}


def _key(s: dict[str, Any]) -> set[str]:
    return tokens(" ".join(str(s.get(k) or "") for k in ("device_name", "device_model", "problem", "title")))


def related_sessions(current: dict[str, Any], others: list[dict[str, Any]], *, min_score: float = 0.3, limit: int = 3):
    cur = _key(current)
    out = []
    for o in others:
        if o.get("id") == current.get("id") or not _key(o):
            continue
        k = _key(o)
        score = len(cur & k) / len(cur | k) if cur | k else 0.0
        if (o.get("device_name") or "").lower() and (o.get("device_name") or "").lower() == (current.get("device_name") or "").lower():
            score += 0.2
        if score >= min_score:
            out.append((round(score, 2), o))
    out.sort(key=lambda x: x[0], reverse=True)
    return out[:limit]


def history_block(related: list[tuple[float, dict[str, Any]]], steps_by_session: dict[str, list[dict[str, Any]]]) -> str:
    if not related:
        return ""
    lines = []
    for score, s in related:
        tried = "; ".join(f"{st.get('title')} -> {OUTCOME_LABELS.get(st.get('verification_outcome', 'pending'), 'unknown')}"
                          for st in steps_by_session.get(s["id"], [])[:6]) or "no steps recorded"
        lines.append(f"- {str(s.get('created_at', ''))[:10]} | {s.get('device_name') or 'unknown device'} | issue: "
                     f"{(s.get('problem') or s.get('title') or '')[:120]} | final status: {s.get('final_status') or s.get('workflow_state')} | tried: {tried}")
    return ("PAST SESSIONS (possibly the same recurring issue):\n" + "\n".join(lines) +
            "\nThese are old records, not current facts. Do not assume the earlier diagnosis still applies; "
            "mention what was already tried, avoid repeating failed steps blindly, and re-check with current evidence.")

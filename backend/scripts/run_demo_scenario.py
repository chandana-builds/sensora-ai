"""End-to-end demo scenario (DEMO MODE, simulated): problem -> guided steps -> escalation -> summary -> handoff -> recurrence.
Run from backend/:  python scripts/run_demo_scenario.py"""
import asyncio
import base64
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.ai.config import load_ai_settings                      # noqa: E402
from app.ai.demo_provider_v3 import build_providers_v3          # noqa: E402
from app.services.agent_orchestrator import AgentOrchestrator   # noqa: E402
from app.services.handoff import handoff_markdown                # noqa: E402
from app.services.memory_store import InMemoryMemoryStore        # noqa: E402
from app.services.summary import summary_markdown                # noqa: E402

JPG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 64).decode()
C = "client-demo-0001"


async def main(verbose=True):
    store = InMemoryMemoryStore()
    store.create_session(C, "s1")
    p = build_providers_v3(load_ai_settings({"AI_MODE": "demo", "DEMO_SCENARIO": "router"}))
    o = AgentOrchestrator(store, p)
    script = [("My internet is not working and the router light is orange.", [], False),
              ("I'm a beginner. Here is the router.", [JPG], False),
              ("I've checked the power adapter.", [JPG], True),
              ("I restarted it.", [JPG], True),
              ("I pushed the WAN cable in.", [JPG], True)]
    out = []
    for text, frames, done in script:
        r = await o.handle_turn(C, "s1", NS(text=text, frames=frames, input_mode="text", user_level=None, reported_step_done=done))
        st = r["step"]
        out.append(r)
        if verbose:
            print(f"[{r['workflow_state']:<26}] {r['response']['assistant_message'][:92]}")
            if st:
                print(f"    step: {st['title']} | reported={st['user_reported_complete']} visually_verified={st['visually_verified']} outcome={st['verification_outcome']}")
    summ = o.complete(C, "s1", None)
    if verbose:
        print("\n" + summary_markdown(summ)[:900])
    store.create_session(C, "s2", problem="router internet not working again, orange light")
    rel = o.related(C, "s2")
    if verbose:
        print("\nRelated to new session:", [(r["score"], r["id"], r["status"]) for r in rel])
        print("\n" + handoff_markdown(o.handoff(C, "s1", "local_technician", False))[:700])
    return store, o, out, rel


if __name__ == "__main__":
    asyncio.run(main())

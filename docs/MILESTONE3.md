# Milestone 3: closed-loop agent, memory, handoff

## Files
Backend: `services/{safety_engine,workflow,engine,agent_orchestrator,memory_store,recurrence,summary,handoff,prompt_m3,errors}.py`,
`ai/demo_provider_v3.py`, `routes/agent.py`, `schemas_m3.py`, `scripts/run_demo_scenario.py`, `tests/test_m3_pure.py`,
`supabase/migrations/002_milestone3.sql`. Changed from M2: `ai/factory.py` (lazy Meta import), `services/orchestrator.py` and
`routes/live.py` (errors moved to `services/errors.py`), `components/LiveConsole.tsx` (uses the agent endpoint).
Frontend: `api/agent.ts`, `components/{StepStatus,PrivacyControls,ExperienceSetting,HandoffPanel}.tsx`.

## Wire-up
Superseded by Milestone 4: `app.main:create_app()` mounts every router, builds the store and auth, and `SensoraApp.tsx` wires the UI. See README and docs/DEPLOYMENT.md.

## Endpoints
`POST /sessions/{id}/agent/turn` · `GET /sessions/{id}/memory|summary|related|handoff|evidence` · `POST /sessions/{id}/complete` ·
`POST /sessions/{id}/handoff/export` (needs `consent_to_share`) · `PUT /sessions/{id}/consent` · `DELETE /sessions/{id}/evidence` ·
`GET|PUT /preferences/experience`. (Full table: docs/API.md.)

## Commands
```bash
cd backend
python scripts/run_demo_scenario.py             # full demo scenario, no dependencies
pytest                                          # all tests (needs requirements-dev + requirements-m2)
cd ../frontend && npm run build
```

## Known limitations (Milestone 3 view; see README for the current list)
- Real-mode verification quality depends on the model following the `step_verdict` contract; not tested against live Meta calls.
- Safety is regex-based; negation is handled only for "no/not/without X" forms. It errs toward stopping.
- Recurrence matching is keyword overlap (Jaccard), not semantic.
- Summary and report are template-built (accurate but plain). Evidence images are referenced, not embedded.
- No real technician integration: the pathways only change the report wording and checklist.

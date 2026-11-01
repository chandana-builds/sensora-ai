# Testing

## What exists
| Suite | Needs | Covers |
|---|---|---|
| `tests/test_m2_pure.py` (10), `test_m3_pure.py` (51), `test_m4_pure.py` (21) | Python only | audio/frame validation, safety engine, workflow state machine, verification rules, closed-loop scenario, persistence + restart, recurrence, summary/handoff/consent, config guards, tokens, rate limits, redaction, SQLite **and** the Supabase REST adapter (against `tests/fakes.py`), DB-down and network errors |
| `tests/test_m4_api.py` | `pip install -r requirements-dev.txt` | HTTP: auth on every private route, forged tokens, **cross-user isolation**, full demo flow, hazard stop, input/upload limits (422/413), CORS, rate limit/daily quota, **AI failures (bad key, timeout, outage, rate limit) are reported not faked**, DB down → 503 and degraded health, no internals leaked, no `/docs` in prod, refuses unsafe prod start |
| `tests/test_meta_and_schemas.py` | requirements-dev | Meta request shapes (`/asr/transcribe`, image_url), error mapping, JSON extraction, schema invariants |
| `frontend/e2e/demo.spec.ts` | Node + `npx playwright install chromium` | demo path in a real browser with a fake camera/mic; permission-denied cases |

## Run
```bash
cd backend
python -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt
pytest                                   # everything
python scripts/run_demo_scenario.py      # printed end-to-end scenario, no keys needed
cd ../frontend && npm ci && npx tsc --noEmit && npm run build
npx playwright test                      # starts backend (demo) + vite per playwright.config.ts
python backend/scripts/smoke_test.py <backend-url> --origin <frontend-origin>   # against a deployment
```
## Not automated (do by hand, see DEMO.md)
Real microphone transcription quality, real Meta vision quality, camera on a phone, Safari/iOS behaviour, Render cold start timing.
## Failure cases and where they're tested
Camera/mic denied → e2e (+ hook error text); Meta unavailable/invalid key/network → `test_m4_api` parametrised; database unavailable → `test_m4_pure` + `test_m4_api`; incomplete visual evidence → `test_m3_pure` (poor image/no image never verifies); unsafe situation → `test_m3_pure`, `test_m4_api`; user leaves mid-session → state is saved every turn (`test_m4_pure` restart test), session resumes via `/memory`.

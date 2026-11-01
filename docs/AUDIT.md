# Milestone 4 audit

Scope: the code in this repository (Milestones 2–4 as delivered). **I never had your Milestone 1 repo**, so the M1 pages, `api/client.ts` and M1 migrations were not audited. `SensoraApp.tsx` is a self-contained path that doesn't depend on them.

## Defects found and fixed
| # | Severity | Finding | Fix |
|---|---|---|---|
| 1 | Critical | Identity was a client-chosen `X-Client-Id`: anyone could read another user's sessions by sending their id | Signed guest tokens (HMAC, unguessable) or Supabase-verified tokens; every query scoped by verified owner; foreign ids return 404; tests for isolation |
| 2 | Critical | M2 `turn` route depended on an unwired store (would 501) and duplicated the M3 flow | removed |
| 3 | High | Public deployment had no CORS allow-list, body limit, rate limit, or cost cap | exact-origin CORS (no credentials), ASGI body limit, per-IP/token limits, daily AI quota, session/message caps |
| 4 | High | No production config validation (could run with wildcard CORS / memory store / no auth) | `validate()` fails closed at startup; `scripts/preflight.py` |
| 5 | High | Provider errors raised inside an exception handler would surface as 500 | handler returns JSON with the right status/code; tested |
| 6 | High | (M3, found by tests) the result of the final step was dropped when the model escalated in the same turn; a clarification flag never cleared after the user answered | fixed; regression tests |
| 7 | Medium | Logs could carry tokens/keys (tracebacks, URLs) | redacting filter on all handlers (tokens, bearer, key=value, blobs, exact secrets); access logs are metadata-only |
| 8 | Medium | Unbounded storage growth | quotas + evidence cap/expiry/purge |
| 9 | Low | Dead/duplicate code (M2 orchestrator, store protocol, `safety_gate`, unused schemas/prompt) | removed; tests moved |

## Security review
API keys: server-side only; `check_deploy_config.py` flags server-secret names in frontend code and placeholders in deploy files. CORS: exact origins, no credentials. Input: Pydantic limits, JPEG/WAV validation, 8 MB body cap. AuthN/Z: above. DB policies: RLS on with no policies, public roles revoked, service-role key server-only. Uploads: type/size/duration validated; not executed; images never served back. Logs: redacted.

## Remaining defects / risks (not fixed)
1. React UI, hooks and e2e have never been compiled or run in a browser by me.
2. FastAPI-dependent tests (`test_m4_api.py`, `test_meta_and_schemas.py`) are written but unrun (no packages offline).
3. Supabase adapter verified only against my fake PostgREST, not a real project (new-style API keys unverified).
4. Guests are unverified identities; tokens in `localStorage`; in-memory limits reset on restart.
5. Concurrent turns on one session can race; no optimistic locking.
6. Live verification quality unproven against real Meta output.
7. Sessions abandoned without "End" stay in their last workflow state (history shows it; no auto-expiry).

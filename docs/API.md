# API reference

Base path `/api`. Auth: `Authorization: Bearer <token>`: a guest token from `POST /auth/guest`, or a Supabase access token. Errors: `{"detail": "..."}` or `{"detail": {"code","message","retryable"}}`. A session you don't own returns **404** (same as missing).

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /health/live` | no | liveness (used by Render) |
| `GET /health` | no | deep check: storage reachable, AI mode (`demo` = simulated), auth modes; 503 if the database is down |
| `GET /ai/status` | no | AI mode and model names (drives the DEMO/LIVE badge) |
| `POST /auth/guest` | no | signed guest token (403 if disabled; 10/hour per IP) |
| `GET /auth/me` | yes | who am I (`guest`/`account`) |
| `POST /sessions` `{title?,device_name?,problem?,user_level?}` | yes | create session |
| `GET /sessions` · `GET /sessions/{id}` · `DELETE /sessions/{id}` | yes | history, detail, delete (cascades) |
| `POST /sessions/{id}/agent/turn` `{text,input_mode,frames[<=3 base64 JPEG],user_level?,reported_step_done?}` | yes + daily quota | one troubleshooting turn: safety, vision, reasoning, verification, workflow state |
| `GET /sessions/{id}/memory` | yes | full session for reopening (messages, steps, observations, evidence metadata) |
| `POST /sessions/{id}/complete` `{status?}` | yes | end + save summary |
| `GET /sessions/{id}/summary` · `/related` | yes | summary (JSON+markdown); earlier similar sessions |
| `GET /sessions/{id}/handoff?pathway=&include_evidence=` | yes | technician report preview (nothing shared) |
| `POST /sessions/{id}/handoff/export` `{pathway,include_evidence,consent_to_share,format}` | yes | download `.md`/`.html`; **403 unless `consent_to_share` is true** |
| `PUT /sessions/{id}/consent` `{evidence_consent}` | yes | keep/stop keeping evidence frames (withdrawing deletes them) |
| `GET/DELETE /sessions/{id}/evidence` | yes | list (metadata only) / delete saved frames |
| `GET/PUT /preferences/experience` `{level,remember}` | yes | beginner/experienced; saved only when `remember` is true |
| `POST /transcribe` (multipart `audio` WAV) | yes + daily quota | speech-to-text (503 `demo_no_stt` in demo mode) |
| `GET /me/export` · `DELETE /me/data` | yes | download / erase everything |

Limits: body 8 MB (413); 120 req/min general, 20/min for `agent/turn` and `transcribe` (429 + `Retry-After`); `MAX_TURNS_PER_DAY` per user (default 100); 200 sessions/user and 500 messages/session. AI failures return 502/503/504/429 with a `code` (`auth_failed`, `network_error`, `timeout`, `upstream_error`, `rate_limited`, `invalid_model_output`) and never a made-up answer. Database failure: 503 `database_unavailable`.

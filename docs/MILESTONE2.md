# Milestone 2 — live voice + camera troubleshooting

## What was built
Backend (`backend/app/`): `ai/` (interfaces, Meta provider, demo provider, factory, config), `schemas_ai.py`,
`services/` (orchestrator, safety_gate, audio, prompt, store contract), `routes/live.py`.
Frontend (`frontend/src/`): `components/LiveConsole.tsx(+css)`, hooks (`useLiveCamera`, `usePushToTalk`,
`useSpeechOutput`), `lib/wav.ts`, `lib/frames.ts`, `api/live.ts`.

## Meta API facts used (checked against dev.meta.ai docs, Oct 2026)
- Base `https://api.meta.ai/v1`, `Authorization: Bearer $MODEL_API_KEY`.
- Reasoning + vision: OpenAI-compatible `POST /chat/completions`, model `muse-spark-1.3`, images as
  `image_url` base64 data URLs.
- Speech-to-text: `POST /asr/transcribe`, model `muse-voice-transcribe-1.0`, multipart `request` (JSON: model,
  audioEncoding "WAV", mode "PUSH_TO_TALK", languageBias as language *names*) + `audio` part; mono 16-bit
  16/24 kHz WAV, <=10 min, <=32 MB; transcript returned in `transcript`.
- Meta has no TTS API in these docs, so replies use browser speech synthesis.
- Not confirmed from first-party text: exact multipart field names beyond the above, and the `response_format`
  shape (hence `META_USE_JSON_SCHEMA=false`). Verify with one real call.

## Wiring (the only parts needing your M1 code)
```python
# backend/app/main.py
from app.routes.live import router as live_router
app.include_router(live_router, prefix="/api")
app.state.conversation_store = YourRepoAdapter(...)   # see services/store.py Protocol
```
`YourRepoAdapter` maps four methods to the M1 repositories: `get_session`, `list_messages`, `add_message`
(assistant messages keep the structured JSON in `metadata`), `add_step` (status must stay `awaiting_user`;
`visually_verified` is never set by this milestone). Replace `_client_id()` in `routes/live.py` with M1's
identity dependency. Frontend: render `<LiveConsole sessionId={id} userLevel={prefs.level} />` in the Live page and
align `CLIENT_ID_KEY` in `api/live.ts` with M1's `client.ts`.

## Endpoints
`GET /api/ai/status` · `POST /api/sessions/{id}/turn` · `POST /api/transcribe`

## Honest limits
- Frames are sampled by the user (max 3/turn); no continuous video. Voice is record-then-transcribe, no barge-in
  during recording beyond cancelling speech when the mic is pressed; not full-duplex.
- Demo vision is canned and ignores the image; demo mode has no transcription (type instead).
- Safety rules are keyword/regex based, ignore negation and err toward false alarms. Merge with M1 `safety.py`.
- Two model calls per turn when a frame is attached (vision, then reasoning): added latency by design (separate capabilities).

## Milestone 3 handoff
Technician handoff report from stored messages/steps/observations; Supabase login; step status updates from
user confirmations; session summary generation; optional streaming of the reasoning reply; richer verification
(compare before/after frames) in real mode only.

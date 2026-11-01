# Sensora AI: architecture (after Milestone 3)

```
Browser (React)                          FastAPI                                   Providers
LiveConsole ──POST /agent/turn──▶ AgentOrchestrator ─▶ safety_engine (user text; STOP => model never called)
 StepStatus                         │                 ▶ VisionAnalyzer (sampled frames)      Meta muse-spark / demo
 PrivacyControls                    │                 ▶ Reasoner (JSON)                       Meta muse-spark / demo
 HandoffPanel                       └─▶ engine.apply_turn (pure):
 ExperienceSetting                        normalise ▶ safety_engine on the model's instruction ▶ verify previous step
                                          ▶ one-instruction rule ▶ workflow state ▶ persist via MemoryStore
```

## Modules (backend/app/services)
| Module | Role |
|---|---|
| `safety_engine.py` | allowed / clarification_required / stop_and_escalate for user text and model instructions; never claims physical safety |
| `workflow.py` | 9-state machine + `transition()` guard + `choose_target()` priorities |
| `engine.py` | `decide_verification()` and `apply_turn()`; the only place `visually_verified` can become true |
| `agent_orchestrator.py` | I/O: loads context, calls providers, persists, summary/complete/handoff/export |
| `memory_store.py` | persistence contract + in-memory implementation (tests/demo) |
| `recurrence.py` | finds earlier sessions on the same device/problem and builds the "already tried" block |
| `summary.py`, `handoff.py` | deterministic reports (no model call, so nothing is invented) |

## Verification rules (the core invariant)
- `user_reported_complete` = the user said or clicked that they did it. Never proof of anything.
- `visually_verified` = true only when ALL hold: real mode (not demo), a frame was sent this turn, image quality "good", the model
  returned verdict "succeeded" with a non-empty evidence statement. Otherwise outcome is `user_reported_unverified`, `uncertain`,
  `user_confirmed` (only for steps marked `user_confirmation`, e.g. waiting) or `simulated_not_verified`.
- If a step is unverified, no new step is issued: Sensora asks for a better view. Failed steps lead to the next safe step.
- Demo mode can never set `visually_verified`.

## Privacy
Nothing visual is stored by default. With `evidence_consent` only user-captured frames are kept (max 5/session, 30-day expiry,
no video). Withdrawing consent or DELETE `/evidence` erases them. Reports can be previewed freely; exporting requires
`consent_to_share=true` (HTTP 403 otherwise). Evidence is listed by reference only; images are not embedded. Nothing is sent to anyone.

## Production layer (Milestone 4)
```
Vercel (static React, CSP + Permissions-Policy)  ──HTTPS + Bearer token──▶  Render (FastAPI)  ──REST, service-role key──▶  Supabase Postgres (RLS on, no policies)
                                                                              │  └──▶ Meta Model API (server-side key)
                       Supabase Auth (optional email/password) ◀── token check ──┘
```
Request path: BodyLimit → CORS (outermost) → Guard (request id, rate limit, security headers, redacted access log) → `current_user` (guest HMAC token or Supabase token check) → optional daily quota → route → `DocMemoryStore` (every query filtered by owner). Failures map to explicit codes (`database_unavailable`, `auth_unavailable`, provider errors); nothing is ever answered with invented AI output.
Storage: one document-style store with two interchangeable backends (SQLite for local dev, Supabase REST for production); production refuses to start on `memory`.

## Multi-Provider AI Reliability Architecture

```
                                  ┌──▶ Meta Model API (Primary Vision, Reasoner, STT)
                                  │       │ (timeout / 5xx / 429)
                                  │       ▼
AgentOrchestrator ──▶ MultiProviderRouter ─▶ Google Gemini API (Multimodal Vision, Reasoner)
                                  │       │ (timeout / 5xx / 429)
                                  │       ▼
                                  ├──▶ Groq API (Llama 3.3 Reasoner, Llama 3.2 Vision, Whisper STT)
                                  │       │ (total exhaustion)
                                  │       ▼
                                  └──▶ SafeDeterministicFallbackReasoner (Suspends repair advice, flags caution)
```

### 1. Provider Roles & Modalities
| Provider | Modalities Supported | Models Configured | Fallback Role |
|---|---|---|---|
| **Meta Model API** | Text Reasoning, Multimodal Vision, Speech-to-Text | `muse-spark-1.3`, `muse-voice-transcribe-1.0` | Primary AI provider for all turns |
| **Google Gemini API** | Multimodal Vision, Text Reasoning | `gemini-1.5-flash` | Secondary reasoning & vision fallback |
| **Groq API** | Speech-to-Text, Multimodal Vision, Text Reasoning | `whisper-large-v3`, `llama-3.2-11b-vision-preview`, `llama-3.3-70b-versatile` | Tertiary fallback & ultra-low latency STT fallback |
| **Browser & Local Fallback** | Manual text input, browser Speech APIs | Client Web APIs | Speech input fallback if all server STT fails |
| **Deterministic Safety Fallback** | Safe structured guidance | Local rule engine | Engaged when all external providers fail |

### 2. Capability-Specific Routing & Invariants
- **Vision Routing**: Images are dispatched strictly to providers advertising vision support (`MetaVision`, `GeminiVision`, `GroqVision`). A text-only provider is never sent image frames.
- **Audio Routing**: Audio WAV payloads are routed exclusively to providers supporting audio transcription (`MetaTranscriber`, `GroqTranscriber`). Gemini is not queried for speech. If server STT fails, users are gracefully guided to browser text input.
- **Ordered Fallback**: Configured via `AI_PROVIDER_ORDER=meta,gemini,groq`. Fallback is sequential; providers are never blasted concurrently.
- **Context Preservation**: Full OpenAI-compatible chat history is passed during provider switching, ensuring zero memory loss across turns.

### 3. Circuit Breaker & Health Cooldowns
- **Cooldown Window**: Providers with consecutive transient failures trip the `CircuitBreaker` (default 60s cooldown) and are bypassed without HTTP overhead.
- **Auth & Permission Failures**: HTTP 401/403 or invalid keys mark a provider permanently disabled for the server lifecycle. No retry attempts are made.
- **Rate Limiting & Backoff**: HTTP 429 inspects `Retry-After`. Transient errors (5xx, timeouts) use exponential backoff with jitter up to `AI_MAX_RETRIES`.

### 4. Safety Guarantee
- The Sensora Safety Engine runs independently on raw user input before any provider is invoked. If a safety hazard (gas, fire, shock, water) is detected, provider invocation is bypassed completely, transitioning immediately to `escalation_required` with safety stops.
- When all AI providers fail, `SafeDeterministicFallbackReasoner` returns a caution-level structured response advising the user to pause, avoid opening appliances, and contact certified professionals. No fake AI reasoning is ever emitted.

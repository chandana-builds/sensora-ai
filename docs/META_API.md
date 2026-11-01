# Meta model integration (what is actually used)

Checked against Meta's developer docs (dev.meta.ai) while building; re-verify with one live call before demoing.

| Capability | Endpoint | Model (env var) | Notes |
|---|---|---|---|
| Visual understanding of captured frames | `POST https://api.meta.ai/v1/chat/completions` | `muse-spark-1.3` (`META_VISION_MODEL`) | OpenAI-compatible; frames sent as base64 `image_url` data URLs; JSON reply requested |
| Reasoning / troubleshooting decisions | same endpoint | `muse-spark-1.3` (`META_REASONING_MODEL`) | structured JSON validated server-side |
| Speech-to-text | `POST https://api.meta.ai/v1/asr/transcribe` | `muse-voice-transcribe-1.0` (`META_STT_MODEL`) | multipart: JSON `request` part (model, audioEncoding WAV, mode PUSH_TO_TALK, languageBias) + `audio` part (mono 16-bit 16/24 kHz WAV); transcript in `transcript` |
| Text-to-speech | none used | n/a | no Meta TTS API found in the docs, so replies use the browser's speech synthesis |

Auth: `Authorization: Bearer $MODEL_API_KEY`, server-side only. Vision and reasoning are separate provider interfaces (`ai/base.py`); two model calls happen on a turn that includes a frame.

Not confirmed from first-party text (verify): exact multipart field names beyond the above; the `response_format` JSON-schema shape (so `META_USE_JSON_SCHEMA=false` by default); whether your key has access to every model above; per-call pricing (see your Meta dashboard). Model names are configuration, not code.

"""WAV validation for the Meta transcription endpoint (mono, 16-bit PCM, 16 or 24 kHz)."""
from __future__ import annotations

import io
import wave

MAX_BYTES = 32 * 1024 * 1024   # Meta limit per request
MAX_SECONDS = 120              # our own cap for push-to-talk turns (Meta allows 10 min)
ALLOWED_RATES = (16000, 24000)


class AudioError(ValueError):
    pass


def validate_wav(data: bytes) -> float:
    """Return duration in seconds or raise AudioError with a user-readable reason."""
    if not data:
        raise AudioError("Empty audio upload.")
    if len(data) > MAX_BYTES:
        raise AudioError("Audio is larger than 32 MB.")
    try:
        with wave.open(io.BytesIO(data)) as w:
            ch, width, rate, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    except (wave.Error, EOFError) as exc:
        raise AudioError("Audio must be a valid WAV file.") from exc
    if ch != 1 or width != 2 or rate not in ALLOWED_RATES:
        raise AudioError("WAV must be mono, 16-bit PCM at 16 kHz or 24 kHz.")
    seconds = frames / float(rate)
    if seconds < 0.3:
        raise AudioError("Recording is too short.")
    if seconds > MAX_SECONDS:
        raise AudioError(f"Recording is longer than {MAX_SECONDS} seconds.")
    return seconds


def decode_jpeg_frames(frames_b64: list[str], max_bytes: int = 1_500_000) -> list[bytes]:
    import base64
    import binascii
    out: list[bytes] = []
    for i, f in enumerate(frames_b64):
        try:
            raw = base64.b64decode(f.split(",", 1)[-1], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise AudioError(f"Frame {i + 1} is not valid base64.") from exc
        if not raw.startswith(b"\xff\xd8"):
            raise AudioError(f"Frame {i + 1} is not a JPEG image.")
        if len(raw) > max_bytes:
            raise AudioError(f"Frame {i + 1} is larger than {max_bytes // 1000} KB.")
        out.append(raw)
    return out

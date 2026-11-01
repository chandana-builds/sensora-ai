"""Stdlib-only tests (no FastAPI/Pydantic needed)."""
import base64
import io
import wave

import pytest

from app.ai.config import load_ai_settings
from app.services.audio import AudioError, decode_jpeg_frames, validate_wav


def wav(seconds=1.0, rate=16000, channels=1, width=2):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(channels); w.setsampwidth(width); w.setframerate(rate)
        w.writeframes(b"\x00" * int(seconds * rate) * width * channels)
    return b.getvalue()


def test_wav_ok():
    assert validate_wav(wav(1.0)) == pytest.approx(1.0)
    assert validate_wav(wav(1.0, rate=24000)) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "data",
    [b"", b"not a wav", wav(rate=44100), wav(channels=2), wav(width=1), wav(0.1), wav(130)],
    ids=["empty", "not_wav", "bad_rate", "stereo", "8bit", "too_short", "too_long"],
)
def test_wav_rejected(data):
    with pytest.raises(AudioError):
        validate_wav(data)


def test_frames():
    jpg = b"\xff\xd8\xff" + b"0" * 10
    assert decode_jpeg_frames([base64.b64encode(jpg).decode()]) == [jpg]
    assert decode_jpeg_frames(["data:image/jpeg;base64," + base64.b64encode(jpg).decode()]) == [jpg]
    with pytest.raises(AudioError):
        decode_jpeg_frames([base64.b64encode(b"PNG...").decode()])
    with pytest.raises(AudioError):
        decode_jpeg_frames(["%%%"])



def test_settings_modes():
    assert load_ai_settings({}).effective_mode == "demo"
    assert load_ai_settings({"MODEL_API_KEY": "k"}).effective_mode == "real"
    assert load_ai_settings({"MODEL_API_KEY": "k", "AI_MODE": "demo"}).effective_mode == "demo"
    assert load_ai_settings({"AI_MODE": "real"}).effective_mode == "real"

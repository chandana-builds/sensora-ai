from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class AISettings:
    mode: str               # auto | real | demo
    api_key: str | None     # Meta MODEL_API_KEY
    base_url: str           # Meta base URL
    reasoning_model: str    # Meta reasoning model
    vision_model: str       # Meta vision model
    stt_model: str          # Meta STT model
    stt_language_bias: tuple[str, ...]
    timeout_s: float
    demo_scenario: str      # router | induction
    use_json_schema: bool

    # Multi-provider configuration
    provider_order: tuple[str, ...]
    gemini_api_key: str | None
    gemini_base_url: str
    gemini_model: str
    groq_api_key: str | None
    groq_base_url: str
    groq_reasoning_model: str
    groq_vision_model: str
    groq_stt_model: str
    max_retries: int
    cooldown_s: float

    @property
    def effective_mode(self) -> str:
        if self.mode in ("demo", "real"):
            return self.mode
        return "real" if (self.api_key or self.gemini_api_key or self.groq_api_key) else "demo"

    @property
    def configured_providers(self) -> list[str]:
        configured = []
        for p in self.provider_order:
            if p == "meta" and self.api_key:
                configured.append("meta")
            elif p == "gemini" and self.gemini_api_key:
                configured.append("gemini")
            elif p == "groq" and self.groq_api_key:
                configured.append("groq")
        return configured


def load_ai_settings(env: Mapping[str, str] | None = None) -> AISettings:
    if env is None:
        try:
            from dotenv import find_dotenv, load_dotenv
            load_dotenv(find_dotenv(), override=False)
        except ImportError:
            pass
    e = os.environ if env is None else env
    bias = tuple(s.strip() for s in e.get("META_STT_LANGUAGE_BIAS", "English").split(",") if s.strip())
    order_raw = e.get("AI_PROVIDER_ORDER", "gemini,meta,groq")
    order = tuple(s.strip().lower() for s in order_raw.split(",") if s.strip())

    return AISettings(
        mode=e.get("AI_MODE", "auto").lower(),
        api_key=e.get("MODEL_API_KEY") or None,
        base_url=e.get("META_API_BASE", "https://api.meta.ai/v1").rstrip("/"),
        reasoning_model=e.get("META_REASONING_MODEL", "muse-spark-1.3"),
        vision_model=e.get("META_VISION_MODEL", "muse-spark-1.3"),
        stt_model=e.get("META_STT_MODEL", "muse-voice-transcribe-1.0"),
        stt_language_bias=bias,
        timeout_s=float(e.get("META_TIMEOUT_S", "35")),
        demo_scenario=e.get("DEMO_SCENARIO", "router").lower(),
        use_json_schema=e.get("META_USE_JSON_SCHEMA", "false").lower() == "true",

        provider_order=order or ("gemini", "meta", "groq"),
        gemini_api_key=e.get("GEMINI_API_KEY") or None,
        gemini_base_url=e.get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/"),
        gemini_model=e.get("GEMINI_MODEL", "gemini-2.5-flash"),
        groq_api_key=e.get("GROQ_API_KEY") or None,
        groq_base_url=e.get("GROQ_API_BASE", "https://api.groq.com/openai/v1").rstrip("/"),
        groq_reasoning_model=e.get("GROQ_REASONING_MODEL", "openai/gpt-oss-120b"),
        groq_vision_model=e.get("GROQ_VISION_MODEL", "llama-3.2-11b-vision-preview"),
        groq_stt_model=e.get("GROQ_STT_MODEL", "whisper-large-v3"),
        max_retries=int(e.get("PROVIDER_MAX_RETRIES", "2")),
        cooldown_s=float(e.get("PROVIDER_COOLDOWN_S", "60")),
    )

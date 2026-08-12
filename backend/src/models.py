# src/models.py
import os
from pydantic import BaseModel


class PipelineConfig(BaseModel):
    """Configuration passed down from the frontend per-execution."""

    gender: str = os.getenv("DEFAULT_VOICE_GENDER", "Female")
    speed: str = os.getenv("DEFAULT_SPEECH_SPEED", "1.0")
    tone: str = os.getenv("DEFAULT_SPEECH_TONE", "Announcement")

    # Granular Execution Engines driven by .env variables
    summary_provider: str = os.getenv("DEFAULT_SUMMARY_PROVIDER", "local")
    summary_model: str = os.getenv("DEFAULT_SUMMARY_MODEL", "llama3")

    translation_provider: str = os.getenv("DEFAULT_TRANSLATION_PROVIDER", "local")
    translation_model: str = os.getenv("DEFAULT_TRANSLATION_MODEL", "llama3")

    audio_provider: str = os.getenv("DEFAULT_AUDIO_PROVIDER", "local")
    audio_model: str = os.getenv(
        "DEFAULT_AUDIO_MODEL", "facebook/mms-tts-urd-script_arabic"
    )


class GlobalSettings(BaseModel):
    """Persistent user preferences stored in TinyDB."""

    id: str = "global"
    summary_provider: str = os.getenv("DEFAULT_SUMMARY_PROVIDER", "local")
    summary_model: str = os.getenv("DEFAULT_SUMMARY_MODEL", "llama3")

    translation_provider: str = os.getenv("DEFAULT_TRANSLATION_PROVIDER", "local")
    translation_model: str = os.getenv("DEFAULT_TRANSLATION_MODEL", "llama3")

    audio_provider: str = os.getenv("DEFAULT_AUDIO_PROVIDER", "local")
    audio_model: str = os.getenv(
        "DEFAULT_AUDIO_MODEL", "facebook/mms-tts-urd-script_arabic"
    )

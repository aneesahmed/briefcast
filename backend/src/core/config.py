"""Committed, non-secret application configuration for Briefcast.

Secrets such as GEMINI_API_KEY belong in ``backend/.env``. Operational
defaults and selectable model names live here so the backend and UI share one
source of truth through ``GET /api/config``.
"""

from pathlib import Path


# Project directories
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIST_DIR = PROJECT_DIR / "frontend" / "dist"
BRIEFING_SOURCE_DIR = PROJECT_DIR / "briefing_source"
PROCESSING_FILES_DIR = PROJECT_DIR / "processing_files"
PROCESSED_FILES_DIR = PROJECT_DIR / "processed_files"
FAILED_FILES_DIR = PROJECT_DIR / "failed_files"
INPUT_DOCS_DIR = BRIEFING_SOURCE_DIR
PROCESSING_DOCS_DIR = PROCESSING_FILES_DIR
PROCESSED_DOCS_DIR = PROCESSED_FILES_DIR
LOG_FILE_PATH = PROJECT_DIR / "briefcast.log"

# Web server defaults. Command-line Uvicorn options can still override these
# for one-off runs or deployment environments.
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000
SERVER_RELOAD = True

# Document intake
TEXT_DOCUMENT_EXTENSION = ".txt"
PDF_DOCUMENT_EXTENSION = ".pdf"
DOCX_DOCUMENT_EXTENSION = ".docx"
SUPPORTED_DOCUMENT_EXTENSIONS = (
    TEXT_DOCUMENT_EXTENSION,
    PDF_DOCUMENT_EXTENSION,
    DOCX_DOCUMENT_EXTENSION,
)
DEFAULT_STAGED_FILENAME = "staged_doc.txt"
SCANNER_ENABLED = True
SCANNER_INTERVAL_SECONDS = 10.0

# Gemini text pipeline
SUMMARY_PROVIDER = "cloud"
SUMMARY_MODEL = "gemini-2.5-flash"
SUMMARY_MAX_WORDS = 120
TRANSLATION_PROVIDER = "cloud"
TRANSLATION_MODEL = "gemini-2.5-flash"

# Audio pipeline
AUDIO_PROVIDER = "cloud"
AUDIO_MODEL = "gemini-2.5-flash-preview-tts"
AUDIO_FORMAT = "mp3"
AUDIO_SAMPLE_RATE_HZ = 24_000
MP3_BIT_RATE_KBPS = 128
DEFAULT_VOICE_GENDER = "Female"
DEFAULT_SPEECH_SPEED = "1.0"
DEFAULT_SPEECH_TONE = "Announcement"
GEMINI_VOICE_BY_GENDER = {"Female": "Aoede", "Male": "Puck"}

# Cost estimation. Keep pricing updates here so every endpoint uses the same table.
USD_TO_PKR_FALLBACK = 280.0
MODEL_PRICING = {
    SUMMARY_MODEL: {
        "input_per_million": 0.30,
        "output_per_million": 2.50,
    },
    AUDIO_MODEL: {
        "input_per_million": 0.50,
        "output_per_million": 10.00,
    },
}

# Online model options exposed to React. Add more models to a task tuple here;
# endpoints and frontend selectors read these lists dynamically.
MODEL_OPTIONS = {
    "summary": (SUMMARY_MODEL,),
    "translation": (TRANSLATION_MODEL,),
    "audio": (AUDIO_MODEL,),
}
VOICE_GENDER_OPTIONS = tuple(GEMINI_VOICE_BY_GENDER)
SPEECH_TONE_OPTIONS = ("Announcement", "Neutral")
SPEECH_SPEED_OPTIONS = ("0.9", DEFAULT_SPEECH_SPEED, "1.3")

import os

# Testing configuration
# If APP_MODE is 'test', bypasses real LLM calls and returns static dummy results.
APP_MODE = os.getenv("APP_MODE", "test").lower()
TEST_MODE = APP_MODE != "live"

# Flat artifact naming
SUMMARY_FILE_SUFFIX = "_summary.txt"
TRANSLATION_FILE_SUFFIX = "_translation.txt"
AUDIO_FILE_SUFFIX = f"_audio.{AUDIO_FORMAT}"
MANIFEST_FILE_SUFFIX = "_manifest.json"
ERROR_FILE_SUFFIX = "_error.json"


def public_config() -> dict:
    """Return non-secret configuration safe to expose through the API."""
    return {
        "pipeline_defaults": {
            "summary_provider": SUMMARY_PROVIDER,
            "summary_model": SUMMARY_MODEL,
            "summary_max_words": SUMMARY_MAX_WORDS,
            "translation_provider": TRANSLATION_PROVIDER,
            "translation_model": TRANSLATION_MODEL,
            "audio_provider": AUDIO_PROVIDER,
            "audio_model": AUDIO_MODEL,
            "gender": DEFAULT_VOICE_GENDER,
            "speed": DEFAULT_SPEECH_SPEED,
            "tone": DEFAULT_SPEECH_TONE,
        },
        "model_options": {stage: list(models) for stage, models in MODEL_OPTIONS.items()},
        "voice_options": {
            "genders": list(VOICE_GENDER_OPTIONS),
            "tones": list(SPEECH_TONE_OPTIONS),
            "speeds": list(SPEECH_SPEED_OPTIONS),
        },
        "supported_extensions": list(SUPPORTED_DOCUMENT_EXTENSIONS),
        "audio_format": AUDIO_FORMAT,
        "scanner": {
            "enabled": SCANNER_ENABLED,
            "interval_seconds": SCANNER_INTERVAL_SECONDS,
        },
        "server": {
            "host": SERVER_HOST,
            "port": SERVER_PORT,
        },
    }


for directory in (BRIEFING_SOURCE_DIR, PROCESSING_FILES_DIR, PROCESSED_FILES_DIR, FAILED_FILES_DIR):
    directory.mkdir(parents=True, exist_ok=True)

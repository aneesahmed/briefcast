"""Committed, non-secret application configuration for Briefcast.

Secrets such as GEMINI_API_KEY belong in ``backend/.env``. Operational
defaults and model names live here so deployments use one source of truth.
"""

from pathlib import Path

from dotenv import load_dotenv

# Project directories
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")
BRIEFING_SOURCE_DIR = PROJECT_DIR / "briefing_source"
PROCESSED_FILES_DIR = PROJECT_DIR / "processed_files"
FAILED_FILES_DIR = PROJECT_DIR / "failed_files"
INPUT_DOCS_DIR = BRIEFING_SOURCE_DIR
PROCESSED_DOCS_DIR = PROCESSED_FILES_DIR
LOG_FILE_PATH = PROJECT_DIR / "briefcast.log"

# Web server defaults. Command-line Uvicorn options can still override these
# for one-off runs or deployment environments.
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000
SERVER_RELOAD = False

# Document intake
TEXT_DOCUMENT_EXTENSION = ".txt"
PDF_DOCUMENT_EXTENSION = ".pdf"
DOCX_DOCUMENT_EXTENSION = ".docx"
SUPPORTED_DOCUMENT_EXTENSIONS = (
    TEXT_DOCUMENT_EXTENSION,
    PDF_DOCUMENT_EXTENSION,
    DOCX_DOCUMENT_EXTENSION,
)
SCANNER_ENABLED = True
SCANNER_INTERVAL_SECONDS = 5.0

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
DEFAULT_SPEECH_TONE = "Announcement"
GEMINI_VOICE_BY_GENDER = {"Female": "Aoede", "Male": "Puck"}

# Add more online models to a task tuple when a pipeline stage needs alternatives.
MODEL_OPTIONS = {
    "summary": (SUMMARY_MODEL,),
    "translation": (TRANSLATION_MODEL,),
    "audio": (AUDIO_MODEL,),
}
# Flat artifact naming
SUMMARY_FILE_SUFFIX = "_summary.txt"
TRANSLATION_FILE_SUFFIX = "_translation.txt"
AUDIO_FILE_SUFFIX = f"_audio.{AUDIO_FORMAT}"
MANIFEST_FILE_SUFFIX = "_manifest.json"
ERROR_FILE_SUFFIX = "_error.json"


for directory in (BRIEFING_SOURCE_DIR, PROCESSED_FILES_DIR, FAILED_FILES_DIR):
    directory.mkdir(parents=True, exist_ok=True)

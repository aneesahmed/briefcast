from pathlib import Path

# Project directories
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
BRIEFING_SOURCE_DIR = PROJECT_DIR / "briefing_source"
PROCESSING_FILES_DIR = PROJECT_DIR / "processing_files"
PROCESSED_FILES_DIR = PROJECT_DIR / "processed_files"
FAILED_FILES_DIR = PROJECT_DIR / "failed_files"
LOG_FILE_PATH = PROJECT_DIR / "briefcast.log"

INPUT_DOCS_DIR = BRIEFING_SOURCE_DIR
PROCESSING_DOCS_DIR = PROCESSING_FILES_DIR
PROCESSED_DOCS_DIR = PROCESSED_FILES_DIR

# Models
SUMMARY_MODEL = "gemini-3.7-flash"
TRANSLATION_MODEL = "gemini-3.7-flash"
OCR_MODEL = "gemini-3.7-flash"
AUDIO_MODEL = "gemini-2.5-flash-preview-tts"
# Used dynamically by the pipeline if AUDIO_MODEL reaches its daily quota limits
FALLBACK_AUDIO_MODEL = "gemini-3.1-flash-tts-preview"

MODEL_OPTIONS = {
    "summary": (SUMMARY_MODEL,),
    "translation": (TRANSLATION_MODEL,),
    "audio": (AUDIO_MODEL,),
}

# Flat artifact naming
SUMMARY_FILE_SUFFIX = "_summary.txt"
TRANSLATION_FILE_SUFFIX = "_translation.txt"
AUDIO_FILE_SUFFIX = "_audio.mp3"
MANIFEST_FILE_SUFFIX = "_manifest.json"
ERROR_FILE_SUFFIX = "_error.json"

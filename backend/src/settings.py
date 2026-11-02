from pathlib import Path

# Project directories
BRIEFING_SOURCE_DIR = Path(r"C:\working\AI26\briefcast\briefing_source")
PROCESSING_FILES_DIR = Path(r"C:\working\AI26\briefcast\processing_files")
PROCESSED_FILES_DIR = Path(r"C:\working\AI26\briefcast\processed_files")
FAILED_FILES_DIR = Path(r"C:\working\AI26\briefcast\failed_files")
LOG_FILE_PATH = Path(r"C:\working\AI26\briefcast\briefcast.log")

INPUT_DOCS_DIR = BRIEFING_SOURCE_DIR
PROCESSING_DOCS_DIR = PROCESSING_FILES_DIR
PROCESSED_DOCS_DIR = PROCESSED_FILES_DIR

# Models
SUMMARY_MODEL = "gemini-3.8-flash"
TRANSLATION_MODEL = "gemini-3.8-flash"
OCR_MODEL = "gemini-3.8-flash"
AUDIO_MODEL = "gemini-2.5-flash-preview-tts"

# Fallback models (used dynamically if primary model encounters 429 rate limit or quota limits)
FALLBACK_SUMMARY_MODEL = "gemini-3.7-flash"
FALLBACK_TRANSLATION_MODEL = "gemini-3.7-flash"
FALLBACK_OCR_MODEL = "gemini-3.7-flash"
FALLBACK_AUDIO_MODEL = "gemini-3.1-flash-tts-preview"

# Guardrails for scanned / image-only PDFs and extraction limits
MAX_OCR_PAGES = 10
MAX_SCANNED_PAGES = MAX_OCR_PAGES
MAX_SCANNED_SIZE_MB = 10.0
MAX_TOKEN_LIMIT = 600_000
PAGE_TIER_CUTOFF = 60
EXTRACT_WORKERS = 2

# Minimum size and content guardrails
MIN_FILE_SIZE_BYTES = {
    ".pdf": 2048,   # 2 KB (corrupted/empty PDFs are < 1-2KB)
    ".docx": 3072,  # 3 KB (empty docx archives are > 3KB)
    ".txt": 1,      # 1 Byte (empty 0-byte text files are rejected)
}
MIN_CONTENT_WORDS = 1

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

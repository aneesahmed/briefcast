import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Dynamic Directory Resolution ---
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Read folder names from .env, falling back to defaults if missing
BRIEFING_SOURCE_DIR = BASE_DIR / os.getenv("BRIEFING_SOURCE_DIR", "briefing_source")
PROCESSED_SUBDIR = BRIEFING_SOURCE_DIR / "processed"
# For backwards compatibility with other files if needed
INPUT_DOCS_DIR = BRIEFING_SOURCE_DIR
PROCESSED_DOCS_DIR = PROCESSED_SUBDIR

# Ensure all operational directories exist on startup
BRIEFING_SOURCE_DIR.mkdir(exist_ok=True)
PROCESSED_SUBDIR.mkdir(exist_ok=True)
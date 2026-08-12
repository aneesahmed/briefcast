import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Dynamic Directory Resolution ---
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Read folder names from .env, falling back to defaults if missing
INPUT_DOCS_DIR = BASE_DIR / os.getenv("INPUT_DOCS_DIR", "input_docs")
PROCESSED_DOCS_DIR = BASE_DIR / os.getenv("PROCESSED_DOCS_DIR", "processed_docs")

# Ensure all operational directories exist on startup
INPUT_DOCS_DIR.mkdir(exist_ok=True)
PROCESSED_DOCS_DIR.mkdir(exist_ok=True)
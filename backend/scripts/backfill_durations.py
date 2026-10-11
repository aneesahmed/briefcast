import json
import logging
from pathlib import Path
from mutagen.mp3 import MP3
import sys
import os

# Add backend to path so we can import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.settings import PROCESSED_DOCS_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def backfill():
    processed_dir = Path(PROCESSED_DOCS_DIR)
    manifests = list(processed_dir.glob("*_manifest.json"))
    
    updated_count = 0
    for manifest_path in manifests:
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            if "audio_duration_seconds" in data:
                continue
                
            audio_file = data.get("audio_file")
            if not audio_file:
                continue
                
            audio_path = processed_dir / audio_file
            if not audio_path.exists():
                continue
                
            # Calculate duration
            audio_obj = MP3(str(audio_path))
            duration = round(audio_obj.info.length, 2)
            
            # Update and save
            data["audio_duration_seconds"] = duration
            
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                
            updated_count += 1
            if updated_count % 50 == 0:
                logger.info(f"Updated {updated_count} manifests...")
                
        except Exception as e:
            logger.error(f"Error processing {manifest_path.name}: {e}")
            
    logger.info(f"Successfully backfilled durations for {updated_count} legacy files!")

if __name__ == "__main__":
    backfill()

from tinydb import TinyDB
from src.core.config import PROCESSED_DOCS_DIR

def update_settings():
    db_file = PROCESSED_DOCS_DIR / "briefcast_db.json"
    db = TinyDB(db_file)
    settings_table = db.table("settings")
    
    new_settings = {
        "id": "global",
        "summary_provider": "cloud",
        "summary_model": "gemini-2.5-flash",
        "translation_provider": "cloud",
        "translation_model": "gemini-2.5-flash",
        "audio_provider": "cloud",
        "audio_model": "gemini-2.5-flash-preview-tts"
    }
    
    if settings_table.contains(doc_id=1):
        settings_table.update(new_settings, doc_ids=[1])
    else:
        settings_table.insert(new_settings)
        
    print("DB successfully updated!")

if __name__ == "__main__":
    update_settings()

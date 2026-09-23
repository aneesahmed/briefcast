import json
import glob
from pathlib import Path

# Adjust this path if your processed_files folder is elsewhere
PROCESSED_DIR = Path("processed_files")

def update_manifests():
    if not PROCESSED_DIR.exists():
        print(f"Error: Could not find directory '{PROCESSED_DIR.absolute()}'.")
        return

    manifest_files = list(PROCESSED_DIR.glob("*_manifest.json"))
    if not manifest_files:
        print(f"No manifest files found in {PROCESSED_DIR.absolute()}")
        return

    updated_count = 0
    for file_path in manifest_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            needs_update = False
            
            # Check if body tag is missing or set to old value
            if data.get("body") != "Voice Attached":
                data["body"] = "Voice Attached"
                needs_update = True
                
            if needs_update:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                updated_count += 1
                
        except Exception as e:
            print(f"Failed to process {file_path.name}: {e}")

    print(f"Scan complete! Updated {updated_count} out of {len(manifest_files)} manifest files.")

if __name__ == "__main__":
    update_manifests()

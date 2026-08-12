# src/main_clone.py
import os
from pathlib import Path
from dotenv import load_dotenv
from voice_cloner import generate_voice_cloning_key, synthesize_with_cloned_voice
from translator import get_or_create_urdu_translation

load_dotenv()

# Define project root dynamically (parent directory of 'src')
ROOT_DIR = Path(__file__).resolve().parent.parent

def run_pipeline():
    # Explicitly map asset paths outside the src folder
    reference_audio = str(ROOT_DIR / "assets" / "reference_voice.wav")
    consent_audio = str(ROOT_DIR / "assets" / "consent_audio.wav")

    print(f"-> Looking for reference audio at: {reference_audio}")
    print(f"-> Looking for consent audio at: {consent_audio}")

    # 1. Generate your unique voice cloning key
    voice_key = generate_voice_cloning_key(reference_audio, consent_audio)

    # 2. Fetch your target text script
    script_text = get_or_create_urdu_translation()

    # 3. Generate speech matching the custom voice clone
    output_path = str(ROOT_DIR / "pakistani_cloned_demo.wav")
    synthesize_with_cloned_voice(voice_key, script_text, output_filename=output_path)

if __name__ == "__main__":
    run_pipeline()
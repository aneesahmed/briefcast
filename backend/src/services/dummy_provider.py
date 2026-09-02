import asyncio
from pathlib import Path

def run_dummy_extraction() -> dict:
    """Returns static JSON extraction mimicking the Gemini extraction node."""
    return {
        "extracted_data": {
            "company_name": "Dummy Company",
            "symbol": "DUMMY",
            "reporting_period": "Q1",
            "document_classification": "Dummy Report",
            "currency_scale": "Millions",
            "key_metrics": [],
            "corporate_actions": None
        },
        "extracted_name": "Dummy Company"
    }

def run_dummy_drafting() -> dict:
    """Returns a static English script mimicking the drafting node."""
    return {"english_script": "dummy summary for functional testing"}

def run_dummy_translation() -> dict:
    """Returns a static Urdu script mimicking the translation node."""
    return {"urdu_script": "dummy translation for func test"}

def run_dummy_audio(output_file: Path, audio_path: str) -> dict:
    """Writes a dummy MP3 file and returns metrics mimicking the audio generation node."""
    dummy_mp3_path = Path(__file__).resolve().parent.parent.parent / "assets" / "dummy_audio.mp3"
    if dummy_mp3_path.exists():
        with open(dummy_mp3_path, "rb") as f_in:
            with open(output_file, "wb") as f_out:
                f_out.write(f_in.read())
    else:
        # Fallback to creating a zero-byte file if dummy_audio.mp3 is missing
        output_file.touch()
        
    return {
        "audio_path": audio_path,
        "audio_metrics": {
            "characters": 35,
            "duration_seconds": 0.1,
            "provider": "dummy",
            "model": "dummy-audio",
        },
    }

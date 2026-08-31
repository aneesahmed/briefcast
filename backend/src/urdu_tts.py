# src/urdu_tts.py
from google import genai
from google.genai import types
import wave
from dotenv import load_dotenv
from translator import get_or_create_urdu_translation
from src.core.config import (
    AUDIO_MODEL,
    AUDIO_SAMPLE_RATE_HZ,
    DEFAULT_VOICE_GENDER,
    GEMINI_VOICE_BY_GENDER,
)

load_dotenv()
client = genai.Client()


def generate_urdu_audio():
    # 1. Fetch text (from local cache or API translator)
    urdu_transcript = get_or_create_urdu_translation()

    print(f"\nGenerating Audio via {AUDIO_MODEL}...")

    audio_prompt = (
        f"Speak the following text naturally and clearly:\n\n{urdu_transcript}"
    )

    # 2. Call the TTS model with the required AUDIO response modality
    response = client.models.generate_content(
        model=AUDIO_MODEL,
        contents=audio_prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],  # Required for TTS preview models
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=GEMINI_VOICE_BY_GENDER[DEFAULT_VOICE_GENDER]
                    )
                )
            ),
        ),
    )

    # 3. Save the output to a WAV file
    audio_data = response.candidates[0].content.parts[0].inline_data.data

    with wave.open("urdu_demo.wav", "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(AUDIO_SAMPLE_RATE_HZ)
        wf.writeframes(audio_data)

    print("\nSuccess! Demo saved to urdu_demo.wav")


if __name__ == "__main__":
    generate_urdu_audio()

from google import genai
from google.genai import types
import wave
from dotenv import load_dotenv
from prompts import get_informational_prompt
from src.core.config import (
    AUDIO_MODEL,
    AUDIO_SAMPLE_RATE_HZ,
    DEFAULT_VOICE_GENDER,
    GEMINI_VOICE_BY_GENDER,
)
# Load the environment variables from the .env file
load_dotenv()

# Initialize the new SDK client (it automatically picks up GEMINI_API_KEY from .env)
client = genai.Client()

# Set up your dialogue or text
transcript =  get_informational_prompt()

# Call the 2.5 TTS model
response = client.models.generate_content(
    model=AUDIO_MODEL,
    contents=transcript,
    config=types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=GEMINI_VOICE_BY_GENDER[DEFAULT_VOICE_GENDER]
                )
            )
        )
    )
)

# Save the output to a WAV file
with wave.open("gemini_demo.wav", "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(AUDIO_SAMPLE_RATE_HZ)
    # The new SDK parses the response structure slightly differently
    wf.writeframes(response.candidates[0].content.parts[0].inline_data.data)

print("Demo saved to gemini_demo.wav")

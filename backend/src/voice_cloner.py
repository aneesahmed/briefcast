# src/voice_cloner.py
import os
import base64
import requests
from dotenv import load_dotenv
import google.auth
import google.auth.transport.requests
from google.cloud import texttospeech_v1beta1 as texttospeech

load_dotenv()

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")

# Chirp 3 requires a regional endpoint (e.g., "us" or "europe-west2")
TTS_LOCATION = "us"
API_ENDPOINT = f"{TTS_LOCATION}-texttospeech.googleapis.com"


def get_access_token() -> str:
    """Retrieves access token using service account or ADC credentials."""
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    return credentials.token


def file_to_base64(file_path: str) -> str:
    """Encodes a local audio file into a base64 string."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def generate_voice_cloning_key(reference_audio_path: str, consent_audio_path: str) -> str:
    """Generates a Chirp 3 Voice Cloning Key via the regional v1beta1 REST endpoint."""
    token = get_access_token()
    url = f"https://{API_ENDPOINT}/v1beta1/voices:generateVoiceCloningKey"

    ref_base64 = file_to_base64(reference_audio_path)
    consent_base64 = file_to_base64(consent_audio_path)

    request_body = {
        "reference_audio": {
            "audio_config": {"audio_encoding": "LINEAR16"},
            "content": ref_base64,
        },
        "voice_talent_consent": {
            "audio_config": {"audio_encoding": "LINEAR16"},
            "content": consent_base64,
        },
        "consent_script": (
            "I am the owner of this voice and I consent to Google using "
            "this voice to create a synthetic voice model."
        ),
        "language_code": "en-US",
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "x-goog-user-project": PROJECT_ID,
        "Content-Type": "application/json; charset=utf-8",
    }

    print("-> Requesting voice cloning key from Chirp 3 API...")
    response = requests.post(url, headers=headers, json=request_body)

    if not response.ok:
        print("API Error Response:", response.status_code, response.text)
        response.raise_for_status()

    data = response.json()
    voice_key = data.get("voiceCloningKey")
    print("-> Successfully generated voice cloning key!")
    return voice_key


def synthesize_with_cloned_voice(
    voice_key: str, text_script: str, output_filename: str = "cloned_output.wav"
):
    """Synthesizes speech using the generated Voice Cloning Key via Google Cloud SDK."""
    client = texttospeech.TextToSpeechClient()

    input_text = texttospeech.SynthesisInput(text=text_script)

    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        voice_clone=texttospeech.VoiceCloneParams(voice_cloning_key=voice_key),
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        sample_rate_hertz=24000,
    )

    print(f"-> Synthesizing speech with cloned voice into {output_filename}...")
    response = client.synthesize_speech(
        input=input_text, voice=voice, audio_config=audio_config
    )

    with open(output_filename, "wb") as out:
        out.write(response.audio_content)

    print(f"-> Audio successfully saved to {output_filename}")
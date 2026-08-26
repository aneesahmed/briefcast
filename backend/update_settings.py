import requests

data = {
    "summary_provider": "gemini",
    "summary_model": "gemini-3.5-flash",
    "translation_provider": "gemini",
    "translation_model": "gemini-3.5-flash",
    "audio_provider": "gemini",
    "audio_model": "gemini-3.1-flash-tts-preview",
    "gender": "Male"
}

try:
    res = requests.post("http://localhost:8000/api/settings", json=data)
    print("Status Code:", res.status_code)
    print("Response:", res.text)
except Exception as e:
    print("Error:", e)

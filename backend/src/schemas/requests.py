import os
from pydantic import BaseModel

class AudioConfig(BaseModel):
    gender: str = os.getenv("DEFAULT_VOICE_GENDER", "Female")
    speed: str = os.getenv("DEFAULT_SPEECH_SPEED", "1.0")
    tone: str = os.getenv("DEFAULT_SPEECH_TONE", "Announcement")

class EstimateRequest(BaseModel):
    text: str
    model_name: str = "gemini-2.5-flash"
    expected_output_tokens: int = 50

class ProcessTextRequest(BaseModel):
    text: str
    model_name: str = "gemini-2.5-flash"
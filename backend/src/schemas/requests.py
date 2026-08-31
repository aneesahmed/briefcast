from pydantic import BaseModel

from src.core.config import DEFAULT_SPEECH_SPEED, DEFAULT_SPEECH_TONE, DEFAULT_VOICE_GENDER, SUMMARY_MODEL

class AudioConfig(BaseModel):
    gender: str = DEFAULT_VOICE_GENDER
    speed: str = DEFAULT_SPEECH_SPEED
    tone: str = DEFAULT_SPEECH_TONE

class EstimateRequest(BaseModel):
    text: str
    model_name: str = SUMMARY_MODEL
    expected_output_tokens: int = 50

class ProcessTextRequest(BaseModel):
    text: str
    model_name: str = SUMMARY_MODEL

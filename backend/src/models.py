# src/models.py
from pydantic import BaseModel, field_validator
from typing import List, Literal, Optional

from src.core.config import (
    AUDIO_MODEL,
    AUDIO_PROVIDER,
    DEFAULT_SPEECH_SPEED,
    DEFAULT_SPEECH_TONE,
    DEFAULT_VOICE_GENDER,
    MODEL_OPTIONS,
    SUMMARY_MAX_WORDS,
    SUMMARY_MODEL,
    SUMMARY_PROVIDER,
    TRANSLATION_MODEL,
    TRANSLATION_PROVIDER,
)


class PipelineConfig(BaseModel):
    """Configuration passed down from the frontend per-execution."""

    gender: str = DEFAULT_VOICE_GENDER
    speed: str = DEFAULT_SPEECH_SPEED
    tone: str = DEFAULT_SPEECH_TONE

    summary_provider: Literal["cloud"] = SUMMARY_PROVIDER
    summary_model: str = SUMMARY_MODEL
    summary_max_words: int = SUMMARY_MAX_WORDS

    translation_provider: Literal["cloud"] = TRANSLATION_PROVIDER
    translation_model: str = TRANSLATION_MODEL

    audio_provider: Literal["cloud"] = AUDIO_PROVIDER
    audio_model: str = AUDIO_MODEL

    @field_validator("summary_model")
    @classmethod
    def validate_summary_model(cls, value: str) -> str:
        if value not in MODEL_OPTIONS["summary"]:
            raise ValueError("Unsupported online summary model")
        return value

    @field_validator("translation_model")
    @classmethod
    def validate_translation_model(cls, value: str) -> str:
        if value not in MODEL_OPTIONS["translation"]:
            raise ValueError("Unsupported online translation model")
        return value

    @field_validator("audio_model")
    @classmethod
    def validate_audio_model(cls, value: str) -> str:
        if value not in MODEL_OPTIONS["audio"]:
            raise ValueError("Unsupported online audio model")
        return value


class GlobalSettings(BaseModel):
    """Persistent user preferences stored in TinyDB."""

    id: str = "global"
    summary_provider: Literal["cloud"] = SUMMARY_PROVIDER
    summary_model: str = SUMMARY_MODEL
    summary_max_words: int = SUMMARY_MAX_WORDS

    translation_provider: Literal["cloud"] = TRANSLATION_PROVIDER
    translation_model: str = TRANSLATION_MODEL

    audio_provider: Literal["cloud"] = AUDIO_PROVIDER
    audio_model: str = AUDIO_MODEL

    @field_validator("summary_model")
    @classmethod
    def validate_summary_model(cls, value: str) -> str:
        if value not in MODEL_OPTIONS["summary"]:
            raise ValueError("Unsupported online summary model")
        return value

    @field_validator("translation_model")
    @classmethod
    def validate_translation_model(cls, value: str) -> str:
        if value not in MODEL_OPTIONS["translation"]:
            raise ValueError("Unsupported online translation model")
        return value

    @field_validator("audio_model")
    @classmethod
    def validate_audio_model(cls, value: str) -> str:
        if value not in MODEL_OPTIONS["audio"]:
            raise ValueError("Unsupported online audio model")
        return value

class FinancialMetric(BaseModel):
    metric_name: str
    current_period_value: str
    comparative_period_value: str
    variance_percentage: Optional[str]

class CorporateAction(BaseModel):
    event_type: str
    dividend_per_share: Optional[str]
    book_closure_start: Optional[str]
    book_closure_end: Optional[str]

class FinancialReportExtraction(BaseModel):
    document_classification: str 
    company_name: str
    symbol: Optional[str] = None
    reporting_period: str
    currency_scale: str
    key_metrics: List[FinancialMetric]
    corporate_actions: Optional[CorporateAction]

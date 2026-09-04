import asyncio
import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict

from google import genai
from google.genai import types

from src.core.config import (
    AUDIO_MODEL,
    AUDIO_PROVIDER,
    AUDIO_SAMPLE_RATE_HZ,
    DEFAULT_SPEECH_TONE,
    DEFAULT_VOICE_GENDER,
    GEMINI_VOICE_BY_GENDER,
    MP3_BIT_RATE_KBPS,
    SUMMARY_MAX_WORDS,
    SUMMARY_MODEL,
    TRANSLATION_MODEL,
)
from src.models import FinancialReportExtraction


class DocumentState(TypedDict, total=False):
    raw_text: str
    filename: str
    output_dir: Path
    english_summary: str
    urdu_summary: str
    audio_path: str
    pipeline_config: dict[str, Any]
    summary_metrics: dict[str, Any]
    translation_metrics: dict[str, Any]
    audio_metrics: dict[str, Any]


@lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    """Reuse one Gemini client across scanner iterations."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    return genai.Client(api_key=api_key)


def limit_words(text: str, maximum: int = SUMMARY_MAX_WORDS) -> str:
    return " ".join(text.strip().split()[:maximum])


def extract_financial_data(text: str, model: str) -> dict[str, Any]:
    response = get_gemini_client().models.generate_content(
        model=model,
        contents=[
            text,
            "Extract the company name, stock symbol when present, financial results, and corporate actions from this document.",
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FinancialReportExtraction,
            temperature=0.0,
        ),
    )
    if response.parsed is None:
        raise ValueError("Gemini returned no structured financial data")
    if hasattr(response.parsed, "model_dump"):
        return response.parsed.model_dump()
    return dict(response.parsed)


def draft_summary(data: dict[str, Any], model: str, maximum_words: int) -> str:
    prompt = (
        "Write one concise English financial broadcast paragraph from the JSON data below. "
        f"Use active voice and no more than {maximum_words} words. "
        "Preserve all important names, figures, dates, and corporate actions.\n\n"
        f"Data: {json_text(data)}"
    )
    response = get_gemini_client().models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2),
    )
    if not response.text:
        raise ValueError("Gemini returned no English summary")
    return limit_words(response.text, maximum_words)


def translate_summary(summary: str, model: str) -> str:
    prompt = (
        "Translate this financial broadcast into formal, natural Pakistani Urdu. "
        "Preserve all company names, numerical values, dates, and financial meaning. "
        "Return only the Urdu translation.\n\n"
        f"{summary}"
    )
    response = get_gemini_client().models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.1),
    )
    if not response.text:
        raise ValueError("Gemini returned no Urdu translation")
    return response.text.strip()


def json_text(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False)


async def summarize_node(state: DocumentState) -> dict[str, Any]:
    started = time.time()
    config = state.get("pipeline_config", {})
    model = config.get("summary_model", SUMMARY_MODEL)
    maximum_words = int(config.get("summary_max_words", SUMMARY_MAX_WORDS))

    extracted_data = await asyncio.to_thread(
        extract_financial_data, state["raw_text"], model
    )
    summary = await asyncio.to_thread(
        draft_summary, extracted_data, model, maximum_words
    )
    return {
        "english_summary": summary,
        "summary_metrics": {
            "duration_seconds": round(time.time() - started, 2),
            "provider": "cloud",
            "model": model,
            "extracted_data": extracted_data,
            "extracted_name": extracted_data.get("company_name"),
        },
    }


async def translate_node(state: DocumentState) -> dict[str, Any]:
    started = time.time()
    config = state.get("pipeline_config", {})
    model = config.get("translation_model", TRANSLATION_MODEL)
    translation = await asyncio.to_thread(
        translate_summary, state["english_summary"], model
    )
    return {
        "urdu_summary": translation,
        "translation_metrics": {
            "duration_seconds": round(time.time() - started, 2),
            "provider": "cloud",
            "model": model,
        },
    }


def write_mp3(pcm_bytes: bytes, output_file: Path, sample_rate: int) -> None:
    import lameenc

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(MP3_BIT_RATE_KBPS)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(1)
    encoder.set_quality(2)
    output_file.write_bytes(encoder.encode(pcm_bytes) + encoder.flush())


async def generate_audio_node(state: DocumentState) -> dict[str, Any]:
    output_file = Path(state["output_dir"]) / state["audio_path"]
    config = state.get("pipeline_config", {})
    provider = config.get("audio_provider", AUDIO_PROVIDER)
    model = config.get("audio_model", AUDIO_MODEL)
    urdu_text = state["urdu_summary"]
    gender = config.get("gender", DEFAULT_VOICE_GENDER)
    tone = config.get("tone", DEFAULT_SPEECH_TONE)
    voice = GEMINI_VOICE_BY_GENDER.get(
        gender, GEMINI_VOICE_BY_GENDER[DEFAULT_VOICE_GENDER]
    )
    started = time.time()

    response = await get_gemini_client().aio.models.generate_content(
        model=model,
        contents=(
            "Read this Urdu text in a clear Pakistani broadcast accent with a "
            f"{tone.lower()} tone:\n\n{urdu_text}"
        ),
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )
    if not response.candidates or not response.candidates[0].content.parts:
        raise ValueError("Gemini returned no audio data")
    inline_data = response.candidates[0].content.parts[0].inline_data
    if inline_data is None or not inline_data.data:
        raise ValueError("Gemini returned an empty audio response")

    await asyncio.to_thread(
        write_mp3, inline_data.data, output_file, AUDIO_SAMPLE_RATE_HZ
    )
    return {
        "audio_path": state["audio_path"],
        "audio_metrics": {
            "characters": len(urdu_text),
            "duration_seconds": round(time.time() - started, 2),
            "provider": provider,
            "model": model,
        },
    }


class DocumentPipeline:
    async def ainvoke(self, initial_state: DocumentState) -> DocumentState:
        state = dict(initial_state)
        state.update(await summarize_node(state))
        state.update(await translate_node(state))
        state.update(await generate_audio_node(state))
        return state


document_graph = DocumentPipeline()

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
    AUDIO_PROVIDER,
    AUDIO_SAMPLE_RATE_HZ,
    DEFAULT_SPEECH_TONE,
    DEFAULT_VOICE_GENDER,
    GEMINI_VOICE_BY_GENDER,
    MP3_BIT_RATE_KBPS,
    SUMMARY_MAX_WORDS,
)
from src.settings import (
    AUDIO_MODEL,
    FALLBACK_AUDIO_MODEL,
    SUMMARY_MODEL,
    TRANSLATION_MODEL,
)
from src.models import FinancialReportExtraction


class DocumentState(TypedDict, total=False):
    raw_text: str
    filename: str
    output_dir: Path
    english_summary: str
    callname: str
    urdu_summary: str
    audio_path: str
    pipeline_config: dict[str, Any]
    ocr_metrics: dict[str, Any]
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


_cached_registry_csv = ""
_last_pkl_mtime = 0.0

def get_registry_csv() -> str:
    global _cached_registry_csv, _last_pkl_mtime
    from scripts.name_calling import StockRegistry, DEFAULT_DB_PATH
    import os
    
    try:
        current_mtime = os.path.getmtime(DEFAULT_DB_PATH)
    except OSError:
        current_mtime = 0.0
        
    if current_mtime != _last_pkl_mtime or not _cached_registry_csv:
        registry = StockRegistry()
        registry_lines = [f"{r.symbol} | {r.company} | {r.callname}" for r in registry.records.values()]
        _cached_registry_csv = "\n".join(registry_lines)
        _last_pkl_mtime = current_mtime
        
    return _cached_registry_csv

def extract_and_draft_summary(text: str, model: str, maximum_words: int) -> tuple[dict[str, Any], dict[str, int]]:
    registry_csv = get_registry_csv()

    prompt = (
        "Extract the title (from the subject line if given, otherwise extract a suitable title from the document). "
        "Extract the formal company name, official stock symbol, and conversational broadcast_callname. "
        "Also extract financial results and corporate actions.\n\n"
        f"Additionally, write one concise English financial broadcast paragraph summarizing the data in english_summary_draft. "
        f"Use active voice and no more than {maximum_words} words. "
        "Refer to the company exclusively by its conversational broadcast_callname in the summary. "
        "Preserve all important figures, dates, and corporate actions in the summary.\n\n"
        "IMPORTANT: Here is the official PSX registry (Symbol | Company | Callname). "
        "You MUST use your semantic understanding to perfectly match the company from the document to this list. "
        "If the company exists in this list, you MUST strictly use its official symbol and official callname from this list instead of inventing one. "
        "If it does not exist in the list, infer the symbol and generate a natural sounding callname (e.g. strip away 'Limited', 'Inc', brackets).\n\n"
        f"PSX REGISTRY:\n{registry_csv}"
    )

    response = get_gemini_client().models.generate_content(
        model=model,
        contents=[
            text,
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FinancialReportExtraction,
            temperature=0.2,
            thinking_config=types.ThinkingConfig(thinking_level="LOW"),
        ),
    )
    if response.parsed is None:
        raise ValueError("Gemini returned no structured financial data")
    
    usage = {
        "input_tokens": getattr(response.usage_metadata, "prompt_token_count", 0) if getattr(response, "usage_metadata", None) else 0,
        "output_tokens": getattr(response.usage_metadata, "candidates_token_count", 0) if getattr(response, "usage_metadata", None) else 0
    }
        
    if hasattr(response.parsed, "model_dump"):
        return response.parsed.model_dump(), usage
    return dict(response.parsed), usage


# draft_summary is now combined into extract_and_draft_summary


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
        config=types.GenerateContentConfig(
            temperature=0.1,
            thinking_config=types.ThinkingConfig(thinking_level="LOW")
        ),
    )
    if not response.text:
        raise ValueError("Gemini returned no Urdu translation")
    usage = {
        "input_tokens": getattr(response.usage_metadata, "prompt_token_count", 0) if getattr(response, "usage_metadata", None) else 0,
        "output_tokens": getattr(response.usage_metadata, "candidates_token_count", 0) if getattr(response, "usage_metadata", None) else 0
    }
    return response.text.strip(), usage


def json_text(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False)


async def summarize_node(state: DocumentState) -> dict[str, Any]:
    if state.get("english_summary"):
        return {"summary_metrics": {"skipped": True, "reason": "Already exists in processed_files"}}

    config = state.get("pipeline_config", {})
    model = config.get("summary_model", SUMMARY_MODEL)
    maximum_words = int(config.get("summary_max_words", SUMMARY_MAX_WORDS))

    started_extract = time.time()
    extracted_data, extract_usage = await asyncio.to_thread(
        extract_and_draft_summary, state["raw_text"], model, maximum_words
    )
    extract_duration = round(time.time() - started_extract, 2)
    
    company_name = extracted_data.get("company_name", "")
    symbol = extracted_data.get("symbol", "")
    
    callname = extracted_data.get("broadcast_callname") or ""
            
    if not callname:
        callname = company_name or symbol or ""
        
    summary = extracted_data.get("english_summary_draft", "")
    summary = limit_words(summary, maximum_words)
    
    return {
        "english_summary": summary,
        "callname": callname,
        "summary_metrics": {
            "duration_seconds": extract_duration,
            "provider": "cloud",
            "model": model,
            "extracted_data": extracted_data,
            "extracted_name": company_name,
            "extracted_title": extracted_data.get("title"),
            "input_tokens": extract_usage["input_tokens"],
            "output_tokens": extract_usage["output_tokens"],
        },
    }


async def translate_node(state: DocumentState) -> dict[str, Any]:
    if state.get("urdu_summary"):
        return {"translation_metrics": {"skipped": True, "reason": "Already exists in processed_files"}}
        
    started = time.time()
    config = state.get("pipeline_config", {})
    model = config.get("translation_model", TRANSLATION_MODEL)
    translation, translation_usage = await asyncio.to_thread(
        translate_summary, state["english_summary"], model
    )
    return {
        "urdu_summary": translation,
        "translation_metrics": {
            "duration_seconds": round(time.time() - started, 2),
            "provider": "cloud",
            "model": model,
            "input_tokens": translation_usage["input_tokens"],
            "output_tokens": translation_usage["output_tokens"],
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


_flash_audio_quota_reset_time = 0.0

async def generate_audio_node(state: DocumentState) -> dict[str, Any]:
    global _flash_audio_quota_reset_time
    urdu_text = state.get("urdu_summary", "")
    if not urdu_text:
        return {"audio_path": "", "audio_metrics": {}}

    config = state.get("pipeline_config", {})
    provider = config.get("audio_provider", AUDIO_PROVIDER)
    model = config.get("audio_model", AUDIO_MODEL)
    output_file = Path(state["output_dir"]) / state["audio_path"]
    
    if output_file.exists():
        return {"audio_metrics": {"skipped": True, "reason": "Already exists in processed_files"}}

    gender = config.get("gender", DEFAULT_VOICE_GENDER)
    tone = config.get("tone", DEFAULT_SPEECH_TONE)
    voice = GEMINI_VOICE_BY_GENDER.get(
        gender, GEMINI_VOICE_BY_GENDER[DEFAULT_VOICE_GENDER]
    )
    started = time.time()
    
    active_model = model
    if model == AUDIO_MODEL and time.time() < _flash_audio_quota_reset_time:
        active_model = FALLBACK_AUDIO_MODEL

    def get_audio_config():
        return types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        )

    for attempt in range(3):
        try:
            response = await get_gemini_client().aio.models.generate_content(
                model=active_model,
                contents=urdu_text,
                config=get_audio_config(),
            )
        except Exception as e:
            error_str = str(e)
            if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                if active_model == model:
                    import re
                    match = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:([\d\.]+)s)?", error_str)
                    delay = 3600 # Default to 1 hour if parsing fails
                    if match:
                        hours = int(match.group(1) or 0)
                        minutes = int(match.group(2) or 0)
                        seconds = float(match.group(3) or 0.0)
                        delay = hours * 3600 + minutes * 60 + seconds
                    _flash_audio_quota_reset_time = time.time() + delay
                    
                    # Switch to fallback model and retry
                    active_model = FALLBACK_AUDIO_MODEL if model == AUDIO_MODEL else model
                    continue
                else:
                    raise ValueError(f"Gemini API Quota Exceeded for fallback model: {e}")
            else:
                if attempt < 2:
                    await asyncio.sleep(2)
                    continue
                raise

        if not getattr(response, "candidates", None):
            if attempt < 2:
                await asyncio.sleep(2)
                continue
            raise ValueError("Gemini returned no candidates.")
            
        candidate = response.candidates[0]
        content = getattr(candidate, "content", None)
        if content is None:
            reason = getattr(candidate, "finish_reason", "unknown")
            if (str(reason) == "FinishReason.OTHER" or str(reason) == "OTHER") and attempt < 2:
                await asyncio.sleep(2)
                continue
            if str(reason) == "FinishReason.OTHER" or str(reason) == "OTHER":
                raise ValueError(f"Gemini TTS preview model failed to generate audio 3 times (FinishReason: OTHER).")
            
            if attempt < 2:
                await asyncio.sleep(2)
                continue
            raise ValueError(f"Gemini returned no audio data (finish reason: {reason}).")
            
        parts = getattr(content, "parts", None)
        if not parts:
            if attempt < 2:
                await asyncio.sleep(2)
                continue
            raise ValueError("Gemini returned content but no parts.")
            
        inline_data = getattr(parts[0], "inline_data", None)
        if inline_data is None or not getattr(inline_data, "data", None):
            if attempt < 2:
                await asyncio.sleep(2)
                continue
            raise ValueError("Gemini returned an empty audio response")
            
        # Success!
        break

    await asyncio.to_thread(
        write_mp3, inline_data.data, output_file, AUDIO_SAMPLE_RATE_HZ
    )
    return {
        "audio_path": state["audio_path"],
        "audio_metrics": {
            "input_tokens": len(urdu_text),
            "output_tokens": 0,
            "duration_seconds": round(time.time() - started, 2),
            "provider": provider,
            "model": model,
        },
    }


class DocumentPipeline:
    async def ainvoke(self, initial_state: DocumentState) -> DocumentState:
        state = dict(initial_state)
        # 1. Fact extraction & English draft (now uses computed callname internally)
        state.update(await summarize_node(state))
        # 2. Translate the polished English script to Urdu
        state.update(await translate_node(state))
        # 3. Generate speech audio from Urdu text
        state.update(await generate_audio_node(state))
        return state


document_graph = DocumentPipeline()
import os
import asyncio
import time
import warnings
from functools import lru_cache
from pathlib import Path
from typing import TypedDict, Dict, Any
from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

warnings.filterwarnings(
    "ignore",
    category=LangChainPendingDeprecationWarning,
)

from langgraph.graph import StateGraph, START, END
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Import your existing scripts and the new formatter
from scripts.name_calling import get_callname
from src.services.text_formatters import inject_callname
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

load_dotenv()


# 1. Define the Graph State
class BriefcastState(TypedDict, total=False):
    document_text: str  # Raw PDF text input
    extracted_data: Dict[str, Any]  # Structured JSON from Gemini
    extracted_name: str  # The formal company name/symbol found
    english_script: str  # The generated English announcement
    urdu_script: str  # The final translated script
    pipeline_config: dict


@lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    """Keep one Gemini client alive for sync and async pipeline requests."""
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def model_from_state(state: BriefcastState, key: str, default: str) -> str:
    return state.get("pipeline_config", {}).get(key, default)


def limit_words(text: str, maximum: int = SUMMARY_MAX_WORDS) -> str:
    words = text.strip().split()
    return " ".join(words[:maximum])


# 2. Node: Extract Financials (Structured Output)
def extraction_node(state: BriefcastState):
    """Bypasses text generation and forces Gemini to output a strict JSON dict."""
    # Note: Import your Pydantic schema here (e.g., FinancialReportExtraction)
    from src.models import FinancialReportExtraction

    response = get_gemini_client().models.generate_content(
        model=model_from_state(state, "summary_model", SUMMARY_MODEL),
        contents=[
            state["document_text"],
            "Extract the company name, stock symbol when present, financial results, and corporate actions from this document."
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FinancialReportExtraction,
            temperature=0.0
        ),
    )

    parsed_data = response.parsed
    return {
        "extracted_data": parsed_data.model_dump(),
        "extracted_name": parsed_data.company_name
    }


# 3. Node: Draft English Announcement
def drafting_node(state: BriefcastState):
    """Generates the initial 30-second English broadcast script."""
    data_context = state["extracted_data"]
    maximum_words = int(
        state.get("pipeline_config", {}).get("summary_max_words", SUMMARY_MAX_WORDS)
    )

    prompt = f"""
    You are a financial news broadcaster. Using the following JSON data, write a 
    single-paragraph financial broadcast announcement with a strict maximum of {maximum_words} words.
    Use active voice and spell out all abbreviations phonetically.

    Data: {data_context}
    """

    response = get_gemini_client().models.generate_content(
        model=model_from_state(state, "summary_model", SUMMARY_MODEL),
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2)
    )

    return {"english_script": limit_words(response.text, maximum_words)}


# 4. Node: Find & Replace Callname
def name_replacement_node(state: BriefcastState):
    """Intercepts the English script and swaps the formal name for the callname."""
    original_name = state.get("extracted_name", "")
    current_script = state.get("english_script", "")

    if original_name:
        # Get the callname from your working pickle loader
        callname = get_callname(original_name)

        # Apply the regex substitution from the text_formatters utility
        updated_script = inject_callname(current_script, original_name, callname)

        return {"english_script": updated_script}

    return {"english_script": current_script}


# 5. Node: Translate to Urdu
def translation_node(state: BriefcastState):
    """Translates the perfectly formatted English script into Urdu."""
    prompt = f"""
    Translate the following financial broadcast script into formal, natural-sounding Urdu.
    Maintain the precise numerical values and the exact company name.

    Script to translate:
    {state['english_script']}
    """

    response = get_gemini_client().models.generate_content(
        model=model_from_state(state, "translation_model", TRANSLATION_MODEL),
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.1)
    )

    return {"urdu_script": response.text}


# 6. Build and Compile the LangGraph
workflow = StateGraph(BriefcastState)

# Add nodes
workflow.add_node("extract", extraction_node)
workflow.add_node("draft_english", drafting_node)
workflow.add_node("replace_callname", name_replacement_node)
workflow.add_node("translate_urdu", translation_node)

# Define edges (The Execution Flow)
workflow.add_edge(START, "extract")
workflow.add_edge("extract", "draft_english")
workflow.add_edge("draft_english", "replace_callname")
workflow.add_edge("replace_callname", "translate_urdu")
workflow.add_edge("translate_urdu", END)

# Compile graph
briefcast_agent = workflow.compile()


# Compatibility layer for the existing FastAPI/frontend three-step contract.
class DocumentState(TypedDict, total=False):
    raw_text: str
    filename: str
    output_dir: Path
    english_summary: str
    urdu_summary: str
    audio_path: str
    pipeline_config: dict
    summary_metrics: Dict[str, Any]
    translation_metrics: Dict[str, Any]
    audio_metrics: Dict[str, Any]


async def summarize_node(state: DocumentState) -> dict:
    """Extract financial data and draft the English broadcast announcement."""
    started = time.time()

    def run_summary() -> dict:
        graph_state: BriefcastState = {
            "document_text": state["raw_text"],
            "extracted_data": {},
            "extracted_name": "",
            "english_script": "",
            "urdu_script": "",
            "pipeline_config": state.get("pipeline_config", {}),
        }
        extracted = extraction_node(graph_state)
        graph_state.update(extracted)
        drafted = drafting_node(graph_state)
        graph_state.update(drafted)
        graph_state.update(name_replacement_node(graph_state))
        return graph_state

    result = await asyncio.to_thread(run_summary)
    config = state.get("pipeline_config", {})
    return {
        "english_summary": result["english_script"],
        "summary_metrics": {
            "duration_seconds": round(time.time() - started, 2),
            "provider": "cloud",
            "model": config.get("summary_model", SUMMARY_MODEL),
            "usage": {},
            "extracted_data": result["extracted_data"],
            "extracted_name": result["extracted_name"],
        },
    }


async def translate_node(state: DocumentState) -> dict:
    """Translate an English financial announcement into Urdu."""
    started = time.time()

    def run_translation() -> str:
        graph_state: BriefcastState = {
            "document_text": state.get("raw_text", ""),
            "extracted_data": {},
            "extracted_name": "",
            "english_script": state["english_summary"],
            "urdu_script": "",
            "pipeline_config": state.get("pipeline_config", {}),
        }
        return translation_node(graph_state)["urdu_script"]

    urdu_script = await asyncio.to_thread(run_translation)
    config = state.get("pipeline_config", {})
    return {
        "urdu_summary": urdu_script,
        "translation_metrics": {
            "duration_seconds": round(time.time() - started, 2),
            "provider": "cloud",
            "model": config.get("translation_model", TRANSLATION_MODEL),
            "usage": {},
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


async def generate_audio_node(state: DocumentState) -> dict:
    """Generate the final MP3 using the configured online Gemini TTS model."""
    config = state.get("pipeline_config", {})
    provider = config.get("audio_provider", AUDIO_PROVIDER)
    audio_model = config.get("audio_model", AUDIO_MODEL)
    output_file = Path(state["output_dir"]) / state["audio_path"]
    urdu_text = state["urdu_summary"]
    started = time.time()

    gender = config.get("gender", DEFAULT_VOICE_GENDER)
    tone = config.get("tone", DEFAULT_SPEECH_TONE)
    voice = GEMINI_VOICE_BY_GENDER.get(
        gender, GEMINI_VOICE_BY_GENDER[DEFAULT_VOICE_GENDER]
    )
    response = await get_gemini_client().aio.models.generate_content(
        model=audio_model,
        contents=f"Read this Urdu text in a clear Pakistani broadcast accent with a {tone.lower()} tone:\n\n{urdu_text}",
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
    audio_bytes = response.candidates[0].content.parts[0].inline_data.data

    await asyncio.to_thread(
        write_mp3, audio_bytes, output_file, AUDIO_SAMPLE_RATE_HZ
    )

    return {
        "audio_path": state["audio_path"],
        "audio_metrics": {
            "characters": len(urdu_text),
            "duration_seconds": round(time.time() - started, 2),
            "provider": provider,
            "model": audio_model,
        },
    }


def create_document_pipeline_graph():
    builder = StateGraph(DocumentState)
    builder.add_node("summarize", summarize_node)
    builder.add_node("translate", translate_node)
    builder.add_node("generate_audio", generate_audio_node)
    builder.add_edge(START, "summarize")
    builder.add_edge("summarize", "translate")
    builder.add_edge("translate", "generate_audio")
    builder.add_edge("generate_audio", END)
    return builder.compile()


document_graph = create_document_pipeline_graph()

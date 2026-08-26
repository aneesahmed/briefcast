# src/services/agent_graph.py
import os
import wave
import asyncio
import time
import logging
from pathlib import Path
from typing import TypedDict, Dict, Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END

from src.prompts import get_prompt

load_dotenv()
logger = logging.getLogger("uvicorn.info")


def get_llm(provider: str, model_name: str) -> BaseChatModel:
    if provider == "local":
        return ChatOllama(
            model=model_name, temperature=0.2, base_url="http://localhost:11434"
        )
    else:
        # Explicitly pass the API key to resolve the validation error
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0.2,
            api_key=os.getenv("GEMINI_API_KEY")
        )


class DocumentState(TypedDict):
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


from src.models import FinancialReportExtraction

async def summarize_node(state: DocumentState) -> dict:
    """Stage 1: Extraction Node"""
    config = state.get("pipeline_config", {})
    provider = config.get("summary_provider", "cloud")
    text_model = config.get("summary_model", "gemini-2.5-flash")

    logger.info(f"[Extraction Node] Executing via google-genai | Model: '{text_model}'")
    t0 = time.time()

    client = genai.Client()
    system_instruction = """You are an expert Financial Analyst and Corporate Intelligence Agent. Your role is to ingest, extract, and summarize corporate financial disclosures, quarterly/annual reports, mutual fund results, corporate actions, and investor briefing presentations.

CORE OBJECTIVES:
1. Identify Document Class: Determine if the document is (A) Corporate Financial Statement, (B) Asset Management / Multi-Fund Report, (C) Corporate Action / Dividend / Book Closure Notice, or (D) Corporate Briefing / Investor Deck.
2. Maintain Extreme Numerical Precision: Verify and report the base currency and unit scale (e.g., PKR in '000, PKR in Millions). Never extrapolate or round without stating the exact reported number.
3. Zero-Hallucination Policy: Extract only figures and decisions explicitly mentioned. If an item is "NIL", record it as NIL."""

    # Using the google-genai SDK to enforce structured output via response_schema
    response = await client.aio.models.generate_content(
        model=text_model,
        contents=state["raw_text"],
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=FinancialReportExtraction,
            temperature=0.0
        )
    )

    t1 = time.time()
    logger.info(f"[Extraction Node] Completed in {t1 - t0:.2f}s")
    
    extracted_json = response.text
    
    # Fallback usage
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    return {
        "english_summary": extracted_json,
        "summary_metrics": {
            "usage": usage,
            "provider": provider,
            "model": text_model,
        },
    }


async def translate_node(state: DocumentState) -> dict:
    """Stage 2: Scripting Node"""
    config = state.get("pipeline_config", {})
    provider = config.get("translation_provider", "cloud")
    text_model = config.get("translation_model", "gemini-2.5-flash")

    logger.info(f"[Scripting Node] Executing via google-genai | Model: '{text_model}'")
    t0 = time.time()

    client = genai.Client()
    
    scripting_prompt = f"""You are a financial broadcast scriptwriter.
Given the following extracted financial JSON payload, generate a single-paragraph, broadcast-ready audio script in Urdu (written in Urdu script).

CRITICAL CONSTRAINTS:
1. The script MUST be strictly capped at 90 words to fit a 30-second TTS read at 1.3x speed.
2. Route the extracted JSON payload to the matching Markdown template (A, B, C, or D) conceptually based on the document_classification.
3. Spell out ALL financial acronyms (e.g., PSX, SECP, FBR) phonetically in Urdu for seamless text-to-speech generation.
4. Output ONLY the Urdu script paragraph. No preamble, no english text.

JSON Payload:
{state['english_summary']}
"""

    response = await client.aio.models.generate_content(
        model=text_model,
        contents=scripting_prompt,
        config=types.GenerateContentConfig(
            temperature=0.2
        )
    )

    t1 = time.time()
    logger.info(f"[Scripting Node] Completed in {t1 - t0:.2f}s")
    
    urdu_script = response.text.strip()
    
    # Fallback usage
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    return {
        "urdu_summary": urdu_script,
        "translation_metrics": {
            "usage": usage,
            "provider": provider,
            "model": text_model,
        },
    }


async def generate_audio_node(state: DocumentState) -> dict:
    config = state.get("pipeline_config", {})
    provider = config.get("audio_provider", "local")
    audio_model = config.get("audio_model", "facebook/mms-tts-urd-script_arabic")
    gender = config.get("gender", "Female")
    tone = config.get("tone", "Announcement")

    output_file = state["output_dir"] / state["audio_path"]
    char_count = len(state["urdu_summary"])

    if provider == "local":
        logger.info(
            f"[Audio Node] Synthesizing TTS via Local HuggingFace ({audio_model})"
        )
        t0 = time.time()

        def save_local_audio():
            import torch
            import scipy.io.wavfile
            from transformers import VitsModel, AutoTokenizer

            tts_model_id = (
                audio_model if audio_model else "facebook/mms-tts-urd-script_arabic"
            )

            tokenizer = AutoTokenizer.from_pretrained(tts_model_id)
            model = VitsModel.from_pretrained(tts_model_id)

            inputs = tokenizer(state["urdu_summary"], return_tensors="pt")
            with torch.no_grad():
                output = model(**inputs).waveform

            audio_data = output.squeeze().cpu().numpy()
            scipy.io.wavfile.write(
                str(output_file), rate=model.config.sampling_rate, data=audio_data
            )

        await asyncio.to_thread(save_local_audio)
        audio_metrics = {
            "characters": char_count,
            "provider": provider,
            "model": audio_model,
        }

    else:
        client = genai.Client()
        logger.info(
            f"[Audio Node] Synthesizing TTS via Google Cloud | Model: '{audio_model}'"
        )
        t0 = time.time()

        gemini_voice = "Aoede" if gender == "Female" else "Puck"
        audio_prompt = f"Read the following Urdu text with a clear, native Pakistani broadcast accent. Deliver the speech using a {tone.lower()} tone. \n\nText:\n{state['urdu_summary']}"

        response = await client.aio.models.generate_content(
            model=audio_model,
            contents=audio_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=gemini_voice
                        )
                    )
                ),
            ),
        )

        # Safe extraction check to avoid NoneType crashes
        if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
            raise ValueError(f"Gemini Cloud TTS failed to generate audio parts. Response safety block or empty candidates returned: {response}")

        audio_bytes = response.candidates[0].content.parts[0].inline_data.data

        def save_cloud_audio():
            with wave.open(str(output_file), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(audio_bytes)

        await asyncio.to_thread(save_cloud_audio)
        audio_metrics = {
            "characters": char_count,
            "provider": provider,
            "model": audio_model,
        }

    logger.info(f"[Audio Node] Completed in {time.time() - t0:.2f}s")

    # NOTE: the audit DB record is inserted by the caller (routes.py), once, after this
    # node returns — it has the full per-phase telemetry and cumulative cost that this
    # node doesn't have access to. Do not insert here too, or every run double-writes
    # the ledger with one incomplete record and one complete one.

    return {
        "audio_path": state["audio_path"],
        "audio_metrics": audio_metrics,
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
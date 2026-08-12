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


async def summarize_node(state: DocumentState) -> dict:
    config = state.get("pipeline_config", {})
    provider = config.get("summary_provider", "local")
    text_model = config.get("summary_model", "llama3.1")

    logger.info(
        f"[Summarize Node] Executing via {provider.upper()} | Model: '{text_model}'"
    )
    t0 = time.time()

    llm = get_llm(provider, text_model)
    prompt = ChatPromptTemplate.from_messages(
        [("system", get_prompt("summarize_document")), ("human", "{text}")]
    )
    input_text = state["raw_text"]
    response = await (prompt | llm).ainvoke({"text": input_text})

    t1 = time.time()
    logger.info(f"[Summarize Node] Completed in {t1 - t0:.2f}s")

    output_content = response.content.strip()

    # Fallback token estimation for local models if usage_metadata is missing
    usage = response.usage_metadata or {}
    if not usage or usage.get("total_tokens", 0) == 0:
        in_tok = len(input_text) // 4
        out_tok = len(output_content) // 4
        usage = {
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
        }

    return {
        "english_summary": output_content,
        "summary_metrics": {
            "usage": usage,
            "provider": provider,
            "model": text_model,
        },
    }


async def translate_node(state: DocumentState) -> dict:
    config = state.get("pipeline_config", {})
    provider = config.get("translation_provider", "local")
    text_model = config.get("translation_model", "qwen2.5")

    logger.info(
        f"[Translate Node] Executing via {provider.upper()} | Model: '{text_model}'"
    )
    t0 = time.time()

    llm = get_llm(provider, text_model)
    prompt = ChatPromptTemplate.from_messages(
        [("system", get_prompt("translate_to_urdu")), ("human", "{summary}")]
    )
    input_summary = state["english_summary"]
    response = await (prompt | llm).ainvoke({"summary": input_summary})

    t1 = time.time()
    logger.info(f"[Translate Node] Completed in {t1 - t0:.2f}s")

    output_content = response.content.strip()

    # Fallback token estimation for local models if usage_metadata is missing
    usage = response.usage_metadata or {}
    if not usage or usage.get("total_tokens", 0) == 0:
        in_tok = len(input_summary) // 4
        out_tok = len(output_content) // 4
        usage = {
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
        }

    return {
        "urdu_summary": output_content,
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
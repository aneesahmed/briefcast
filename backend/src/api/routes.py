# src/api/routes.py
import asyncio
import json
import os
import shutil
import uuid
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, File, HTTPException, UploadFile, Body, BackgroundTasks, Form
from fastapi.responses import FileResponse
import requests
from tinydb import TinyDB, Query

from src.core.config import INPUT_DOCS_DIR, PROCESSED_DOCS_DIR
from src.cost_calculator import CostCalculator
from src.models import PipelineConfig, GlobalSettings
from src.services.agent_graph import (
    document_graph,
    summarize_node,
    translate_node,
    generate_audio_node,
)
from src.services.document_service import DocumentService

logger = logging.getLogger("uvicorn.info")
router = APIRouter()
calculator = CostCalculator()

db = TinyDB(PROCESSED_DOCS_DIR / "briefcast_db.json")
settings_table = db.table("settings")

ZERO_COST_PRICING = {
    "model_name": "local",
    "input_cost_usd": "$0.000000",
    "output_cost_usd": "$0.000000",
    "total_cost_usd": "$0.000000",
    "total_cost_pkr": "Rs. 0.0000",
    "raw_values": {"total_usd": 0.0, "total_pkr": 0.0, "usd_to_pkr_rate": calculator.usd_to_pkr},
}


def calculate_step_cost(provider: str, model: str, text: str, usage: Optional[Dict[str, Any]] = None):
    """Builds the {text_analytics, pricing_estimation} cost block for one pipeline step.

    Always prefers the real token usage already returned by the LLM call (`usage`)
    over re-deriving it from `text`, so the displayed token count and the cost
    figure next to it are computed from the same numbers.
    """
    usage = usage or {}
    if provider == "local":
        in_tok = usage.get("input_tokens") or len(text) // 4
        out_tok = usage.get("output_tokens") or in_tok
        return {
            "text_analytics": {
                "character_count": len(text),
                "word_count": len(text.split()),
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "total_estimated_tokens": in_tok + out_tok,
            },
            "pricing_estimation": ZERO_COST_PRICING,
        }
    return calculator.calculate_cost_and_metrics(
        text=text,
        model_name=model,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
    )


def _meta_path(output_file: Path) -> Path:
    return output_file.with_suffix(".meta.json")


def _write_step_meta(output_file: Path, metrics: Dict[str, Any], cost: Dict[str, Any]) -> None:
    with open(_meta_path(output_file), "w", encoding="utf-8") as f:
        json.dump({"metrics": metrics, "cost": cost}, f)


def _read_step_meta(output_file: Path) -> Optional[Dict[str, Any]]:
    meta_file = _meta_path(output_file)
    if not meta_file.exists():
        return None
    with open(meta_file, "r", encoding="utf-8") as f:
        return json.load(f)


def _empty_phase_telemetry(provider: str = None, model: str = None) -> Dict[str, Any]:
    return {
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "provider": provider,
        "model": model,
        "cost": {"total_cost_usd": "$0.000000", "total_cost_pkr": "Rs. 0.0000"},
    }


@router.get("/", tags=["Health"])
async def health_check():
    return {"status": "ok"}



@router.get("/api/settings", tags=["Settings"])
async def get_settings():
    record = settings_table.get(doc_id=1)
    if record:
        if record.get("audio_model") == "facebook/mms-tts-urd":
            record["audio_model"] = "facebook/mms-tts-urd-script_arabic"
            settings_table.upsert(record, doc_ids=[1])
        return record
    return GlobalSettings().model_dump()


@router.post("/api/settings", tags=["Settings"])
async def update_settings(settings: GlobalSettings):
    if settings_table.contains(doc_id=1):
        settings_table.update(settings.model_dump(), doc_ids=[1])
    else:
        settings_table.insert(settings.model_dump())
    return {"message": "Settings updated successfully"}


@router.get("/api/history", tags=["Data"])
async def get_history():
    records = db.all()
    records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"history": records}


@router.post("/api/upload-docs", tags=["Data"])
async def upload_documents(files: List[UploadFile] = File(...)):
    saved_files = []
    for file in files:
        try:
            safe_filename = os.path.basename(file.filename)
            with open(INPUT_DOCS_DIR / safe_filename, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_files.append(safe_filename)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"message": f"Successfully uploaded {len(saved_files)} file(s)."}


# ==========================================
# DEDICATED STEP ENDPOINTS WITH CACHING & AUDIT SAVING
# ==========================================


@router.post("/api/step/summary", tags=["React Studio (Step-by-Step)"])
async def step_summary(payload: Dict[str, Any] = Body(...)):
    config = payload.get("config", {})
    filename = payload.get("filename")

    if not filename:
        documents = await asyncio.to_thread(
            DocumentService.read_folder, str(INPUT_DOCS_DIR)
        )
        if not documents:
            raise HTTPException(
                status_code=400, detail="No staged document found in input folder."
            )
        filename = list(documents.keys())[0]

    base_name = Path(filename).stem
    input_file = INPUT_DOCS_DIR / filename
    output_file = PROCESSED_DOCS_DIR / f"{base_name}_summary.txt"

    if output_file.exists() and not payload.get("force"):
        with open(output_file, "r", encoding="utf-8") as f:
            english_summary = f.read()
        cached_meta = _read_step_meta(output_file) or {}
        return {
            "filename": filename,
            "english_summary": english_summary,
            "metrics": cached_meta.get("metrics"),
            "cost": cached_meta.get("cost"),
            "cached": True,
        }

    if not input_file.exists():
        raise HTTPException(status_code=404, detail=f"Input file {filename} not found.")

    with open(input_file, "r", encoding="utf-8") as f:
        raw_text = f.read()

    state = {
        "raw_text": raw_text,
        "filename": filename,
        "output_dir": PROCESSED_DOCS_DIR,
        "english_summary": "",
        "urdu_summary": "",
        "audio_path": "",
        "pipeline_config": config,
        "summary_metrics": {},
        "translation_metrics": {},
        "audio_metrics": {},
    }

    res = await summarize_node(state)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(res["english_summary"])

    provider = config.get("summary_provider", "local")
    model = config.get("summary_model", "llama3.1")
    usage = res["summary_metrics"].get("usage", {})
    cost_info = calculate_step_cost(provider, model, raw_text, usage=usage)
    _write_step_meta(output_file, res["summary_metrics"], cost_info)

    return {
        "filename": filename,
        "english_summary": res["english_summary"],
        "metrics": res["summary_metrics"],
        "cost": cost_info,
        "cached": False,
    }


@router.post("/api/step/translation", tags=["React Studio (Step-by-Step)"])
async def step_translation(payload: Dict[str, Any] = Body(...)):
    config = payload.get("config", {})
    filename = payload.get("filename", "staged_doc.txt")
    english_summary_override = payload.get("english_summary")

    base_name = Path(filename).stem
    input_file = PROCESSED_DOCS_DIR / f"{base_name}_summary.txt"
    output_file = PROCESSED_DOCS_DIR / f"{base_name}_translation.txt"

    if english_summary_override:
        with open(input_file, "w", encoding="utf-8") as f:
            f.write(english_summary_override)
    elif not input_file.exists():
        raise HTTPException(
            status_code=400,
            detail="Summary file not found. Run the summary step first.",
        )

    if output_file.exists() and not payload.get("force"):
        with open(output_file, "r", encoding="utf-8") as f:
            urdu_summary = f.read()
        cached_meta = _read_step_meta(output_file) or {}
        return {
            "filename": filename,
            "urdu_summary": urdu_summary,
            "metrics": cached_meta.get("metrics"),
            "cost": cached_meta.get("cost"),
            "cached": True,
        }

    with open(input_file, "r", encoding="utf-8") as f:
        english_summary = f.read()

    state = {
        "raw_text": "",
        "filename": filename,
        "output_dir": PROCESSED_DOCS_DIR,
        "english_summary": english_summary,
        "urdu_summary": "",
        "audio_path": "",
        "pipeline_config": config,
        "summary_metrics": {},
        "translation_metrics": {},
        "audio_metrics": {},
    }

    res = await translate_node(state)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(res["urdu_summary"])

    provider = config.get("translation_provider", "local")
    model = config.get("translation_model", "qwen2.5")
    usage = res["translation_metrics"].get("usage", {})
    cost_info = calculate_step_cost(provider, model, english_summary, usage=usage)
    _write_step_meta(output_file, res["translation_metrics"], cost_info)

    return {
        "filename": filename,
        "urdu_summary": res["urdu_summary"],
        "metrics": res["translation_metrics"],
        "cost": cost_info,
        "cached": False,
    }


def _phase_telemetry_from_meta(
    meta: Optional[Dict[str, Any]], provider: Optional[str], model: Optional[str]
) -> Dict[str, Any]:
    """Builds one telemetry phase entry from a step's persisted {metrics, cost} sidecar."""
    if not meta:
        return _empty_phase_telemetry(provider, model)
    usage = (meta.get("metrics") or {}).get("usage", {})
    pricing = (meta.get("cost") or {}).get("pricing_estimation", {})
    return {
        "usage": usage,
        "provider": provider,
        "model": model,
        "cost": {
            "total_cost_usd": pricing.get("total_cost_usd", "$0.000000"),
            "total_cost_pkr": pricing.get("total_cost_pkr", "Rs. 0.0000"),
        },
    }


def _phase_raw_cost(meta: Optional[Dict[str, Any]]) -> tuple:
    if not meta:
        return 0.0, 0.0
    raw = (meta.get("cost") or {}).get("pricing_estimation", {}).get("raw_values", {})
    return raw.get("total_usd", 0.0), raw.get("total_pkr", 0.0)


@router.post("/api/step/audio", tags=["React Studio (Step-by-Step)"])
async def step_audio(payload: Dict[str, Any] = Body(...)):
    config = payload.get("config", {})
    filename = payload.get("filename", "staged_doc.txt")
    urdu_summary_override = payload.get("urdu_summary")

    base_name = Path(filename).stem
    input_file = PROCESSED_DOCS_DIR / f"{base_name}_translation.txt"

    # Stable filename (no per-request uuid) so the cache/force toggle actually works,
    # matching the summary/translation steps. The DB transaction still gets its own id.
    audio_filename = f"audio_{base_name}.wav"
    output_file = PROCESSED_DOCS_DIR / audio_filename

    if urdu_summary_override:
        with open(input_file, "w", encoding="utf-8") as f:
            f.write(urdu_summary_override)
    elif not input_file.exists():
        raise HTTPException(
            status_code=400,
            detail="Translation file not found. Run the translation step first.",
        )

    if output_file.exists() and not payload.get("force"):
        cached_meta = _read_step_meta(output_file) or {}
        return {
            "filename": filename,
            "download_url": f"/audio/{audio_filename}",
            "metrics": cached_meta.get("metrics"),
            "cost": cached_meta.get("cost"),
            "cached": True,
        }

    with open(input_file, "r", encoding="utf-8") as f:
        urdu_summary = f.read()

    summary_file = PROCESSED_DOCS_DIR / f"{base_name}_summary.txt"
    english_summary = ""
    if summary_file.exists():
        with open(summary_file, "r", encoding="utf-8") as f:
            english_summary = f.read()

    state = {
        "raw_text": "",
        "filename": filename,
        "output_dir": PROCESSED_DOCS_DIR,
        "english_summary": english_summary,
        "urdu_summary": urdu_summary,
        "audio_path": audio_filename,
        "pipeline_config": config,
        "summary_metrics": {},
        "translation_metrics": {},
        "audio_metrics": {},
    }

    res = await generate_audio_node(state)

    audio_provider = config.get("audio_provider", "local")
    audio_model = config.get("audio_model", "gemini-2.5-flash-preview-tts")

    if audio_provider == "local":
        cost_info = calculate_step_cost(audio_provider, audio_model, urdu_summary)
    else:
        # Gemini TTS bills per output audio token, which isn't known until synthesis
        # completes. We approximate it as the source text's own token count (same
        # order of magnitude as the spoken audio) rather than a fixed guess.
        approx_output_tokens = len(urdu_summary) // 4
        cost_info = calculate_step_cost(
            audio_provider, audio_model, urdu_summary,
            usage={"output_tokens": approx_output_tokens},
        )
    _write_step_meta(output_file, res["audio_metrics"], cost_info)

    # Build the full per-phase telemetry + cumulative cost for the audit record by
    # reading back the summary/translation sidecars written earlier in this pipeline
    # run (rather than trusting transient frontend state, which is lost on reload).
    summary_meta = _read_step_meta(summary_file)
    translation_meta = _read_step_meta(input_file)

    summary_usd, summary_pkr = _phase_raw_cost(summary_meta)
    translation_usd, translation_pkr = _phase_raw_cost(translation_meta)
    audio_usd = cost_info["pricing_estimation"]["raw_values"]["total_usd"]
    audio_pkr = cost_info["pricing_estimation"]["raw_values"]["total_pkr"]
    total_usd = summary_usd + translation_usd + audio_usd
    total_pkr = summary_pkr + translation_pkr + audio_pkr

    transaction_id = str(uuid.uuid4())

    # Save transaction record to DB for Audit Section
    doc_record = {
        "id": transaction_id,
        "transaction_id": transaction_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "filename": filename,
        "english_summary": english_summary,
        "urdu_summary": urdu_summary,
        "audio_file": audio_filename,
        "download_url": f"/audio/{audio_filename}",
        "models_used": {
            "summary_model": config.get("summary_model"),
            "translation_model": config.get("translation_model"),
            "audio_model": audio_model,
        },
        "cost_metrics": {
            "total_cost_usd": f"${total_usd:.6f}",
            "total_cost_pkr": f"Rs. {total_pkr:.4f}",
        },
        "telemetry": {
            "summary_phase": _phase_telemetry_from_meta(
                summary_meta, config.get("summary_provider"), config.get("summary_model")
            ),
            "translation_phase": _phase_telemetry_from_meta(
                translation_meta, config.get("translation_provider"), config.get("translation_model")
            ),
            "audio_phase": {
                "characters": res["audio_metrics"].get("characters", 0),
                "provider": audio_provider,
                "model": audio_model,
                "cost": {
                    "total_cost_usd": cost_info["pricing_estimation"]["total_cost_usd"],
                    "total_cost_pkr": cost_info["pricing_estimation"]["total_cost_pkr"],
                },
            },
        },
    }
    db.insert(doc_record)

    return {
        "filename": filename,
        "download_url": f"/audio/{audio_filename}",
        "metrics": res["audio_metrics"],
        "cost": cost_info,
        "cached": False,
    }


# ==========================================
# CORE BACKGROUND PIPELINE & ASSETS
# ==========================================

@router.get("/audio/{filename}", tags=["Data"])
async def get_audio_file(filename: str):
    file_path = PROCESSED_DOCS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path=file_path, media_type="audio/wav", filename=filename)


async def _run_pipeline_core(
    transaction_id: str,
    filename: str,
    content: str,
    config: PipelineConfig
) -> dict:
    """Core pipeline execution, returns the completed doc_record dict."""
    base_name = Path(filename).stem
    ext = Path(filename).suffix
    source_file = INPUT_DOCS_DIR / filename
    archive_path = PROCESSED_DOCS_DIR / f"{base_name}{ext}"
    audio_filename = f"{base_name}.wav"
    
    start_time = time.time()
    q = Query()
    doc_record = {}

    try:
        pipeline_payload = config.model_dump()
        initial_state = {
            "raw_text": content,
            "filename": filename,
            "output_dir": PROCESSED_DOCS_DIR,
            "english_summary": "",
            "urdu_summary": "",
            "audio_path": audio_filename,
            "pipeline_config": pipeline_payload,
            "summary_metrics": {},
            "translation_metrics": {},
            "audio_metrics": {},
        }

        final_state = await document_graph.ainvoke(initial_state)

        summary_metrics = final_state.get("summary_metrics", {})
        translation_metrics = final_state.get("translation_metrics", {})
        audio_metrics = final_state.get("audio_metrics", {})

        c_sum = calculate_step_cost(
            config.summary_provider, config.summary_model, content,
            usage=summary_metrics.get("usage", {}),
        )
        c_tra = calculate_step_cost(
            config.translation_provider,
            config.translation_model,
            final_state["english_summary"],
            usage=translation_metrics.get("usage", {}),
        )
        if config.audio_provider == "local":
            c_aud = calculate_step_cost(
                config.audio_provider, config.audio_model, final_state["urdu_summary"]
            )
        else:
            approx_output_tokens = len(final_state["urdu_summary"]) // 4
            c_aud = calculate_step_cost(
                config.audio_provider, config.audio_model, final_state["urdu_summary"],
                usage={"output_tokens": approx_output_tokens},
            )

        tot_usd = (
            c_sum["pricing_estimation"]["raw_values"]["total_usd"]
            + c_tra["pricing_estimation"]["raw_values"]["total_usd"]
            + c_aud["pricing_estimation"]["raw_values"]["total_usd"]
        )
        tot_pkr = (
            c_sum["pricing_estimation"]["raw_values"]["total_pkr"]
            + c_tra["pricing_estimation"]["raw_values"]["total_pkr"]
            + c_aud["pricing_estimation"]["raw_values"]["total_pkr"]
        )

        # Save the intermediate text files as requested
        with open(PROCESSED_DOCS_DIR / f"{base_name}_summary.txt", "w", encoding="utf-8") as f:
            f.write(final_state["english_summary"])
            
        with open(PROCESSED_DOCS_DIR / f"{base_name}_translation.txt", "w", encoding="utf-8") as f:
            f.write(final_state["urdu_summary"])

        if source_file.exists():
            shutil.move(str(source_file), str(archive_path))

        total_time = round(time.time() - start_time, 2)
        
        doc_record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "completed",
            "total_time_seconds": total_time,
            "english_summary": final_state["english_summary"],
            "urdu_summary": final_state["urdu_summary"],
            "audio_file": audio_filename,
            "download_url": f"/audio/{audio_filename}",
            "models_used": {
                "summary_model": config.summary_model,
                "translation_model": config.translation_model,
                "audio_model": config.audio_model,
            },
            "cost_metrics": {
                "total_cost_usd": f"${tot_usd:.6f}",
                "total_cost_pkr": f"Rs. {tot_pkr:.4f}",
            },
            "telemetry": {
                "summary_phase": {
                    "usage": summary_metrics.get("usage", {}),
                    "provider": config.summary_provider,
                    "model": config.summary_model,
                },
                "translation_phase": {
                    "usage": translation_metrics.get("usage", {}),
                    "provider": config.translation_provider,
                    "model": config.translation_model,
                },
                "audio_phase": {
                    "characters": audio_metrics.get("characters", 0),
                    "provider": config.audio_provider,
                    "model": config.audio_model,
                }
            }
        }
        db.update(doc_record, q.id == transaction_id)
        doc_record = db.get(q.id == transaction_id)
        logger.info(f"Successfully processed {filename} in {total_time}s.")
        return doc_record

    except Exception as e:
        logger.error(f"Error processing {filename}: {str(e)}")
        total_time = round(time.time() - start_time, 2)
        doc_record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "error",
            "total_time_seconds": total_time,
            "error": str(e)
        }
        db.update(doc_record, q.id == transaction_id)
        return db.get(q.id == transaction_id)


async def _run_pipeline_background(
    transaction_id: str,
    filename: str,
    content: str,
    config: PipelineConfig,
    webhook_url: str
):
    """Background task to run the core pipeline and fire a webhook."""
    doc_record = await _run_pipeline_core(transaction_id, filename, content, config)
    
    if webhook_url and doc_record:
        try:
            def send_webhook():
                requests.post(webhook_url, json=doc_record, timeout=10)
            await asyncio.to_thread(send_webhook)
            logger.info(f"Fired webhook to {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to fire webhook to {webhook_url}: {str(e)}")


@router.get("/api/get_audio", tags=["Audio"])
@router.post("/api/get_audio", tags=["Audio"])
async def get_audio_shared(
    background_tasks: BackgroundTasks,
    file_name: Optional[str] = None,
    job_id: Optional[str] = None
):
    """
    Checks the briefing_source folder for the file. 
    Generates summary, translation, and audio, storing them in the processed subfolder.
    Acts asynchronously and returns status JSON.
    Can be polled by job_id or file_name.
    """
    if not file_name and not job_id:
        raise HTTPException(status_code=400, detail="Must provide file_name or job_id")
        
    q = Query()
    record = None
    
    # 1. Try to find existing job
    if job_id:
        record = db.get(q.id == job_id)
    elif file_name:
        # Get the most recent job for this file_name
        records = db.search(q.filename == file_name)
        if records:
            # Sort by timestamp descending
            records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            record = records[0]
            
    # 2. Return existing job status if it's in progress or completed
    if record and record.get("status") in ["in progress", "completed"]:
        return {
            "job_id": record["id"],
            "file_name": record["filename"],
            "status": record["status"],
            "details": record.get("error") if record["status"] == "error" else None,
            "audio_url": record.get("download_url") if record["status"] == "completed" else None
        }
        
    # 3. Start a new job if not found (or if previous failed)
    if not file_name:
        raise HTTPException(status_code=404, detail="Job not found and no file_name provided to start a new one.")
        
    source_path = INPUT_DOCS_DIR / file_name
    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"File {file_name} not found in shared folder (briefing_source).")
        
    try:
        with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        record_cfg = settings_table.get(doc_id=1)
        config = PipelineConfig(**(record_cfg or GlobalSettings().model_dump()))

        new_job_id = str(uuid.uuid4())
        
        initial_record = {
            "id": new_job_id,
            "transaction_id": new_job_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "in progress",
            "filename": file_name,
            "start_time": time.time()
        }
        db.insert(initial_record)
        
        # Spawn background task. No webhook for this specific endpoint design.
        background_tasks.add_task(_run_pipeline_background, new_job_id, file_name, content, config, None)
        
        return {
            "job_id": new_job_id,
            "file_name": file_name,
            "status": "in progress",
            "details": "Job started successfully."
        }
    except Exception as e:
        logger.error(f"Error starting get_audio job for {file_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))






# src/api/routes.py
import asyncio
from asyncio import Lock

db_lock = Lock()

def get_db():
    return db
import json
import os
import shutil
import uuid
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, File, HTTPException, UploadFile, Body, BackgroundTasks, Query as ApiQuery, Request
from fastapi.responses import FileResponse
import requests

from src.core.config import (
    AUDIO_FILE_SUFFIX,
    AUDIO_MODEL,
    AUDIO_PROVIDER,
    DEFAULT_STAGED_FILENAME,
    ERROR_FILE_SUFFIX,
    FAILED_FILES_DIR,
    INPUT_DOCS_DIR,
    MANIFEST_FILE_SUFFIX,
    PROCESSING_DOCS_DIR,
    PROCESSED_DOCS_DIR,
    PROJECT_DIR,
    LOG_FILE_PATH,
    SCANNER_ENABLED,
    SCANNER_INTERVAL_SECONDS,
    SUMMARY_FILE_SUFFIX,
    SUMMARY_MODEL,
    SUMMARY_PROVIDER,
    SUPPORTED_DOCUMENT_EXTENSIONS,
    TRANSLATION_FILE_SUFFIX,
    TRANSLATION_MODEL,
    TRANSLATION_PROVIDER,
    public_config,
)
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

active_jobs: Dict[str, Dict[str, Any]] = {}

CONFIG_FILE = PROJECT_DIR / "briefcast_config.json"

def get_saved_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


scanner_runtime_enabled = SCANNER_ENABLED
scanner_task: Optional[asyncio.Task] = None
scanner_active_file: Optional[str] = None
scanner_stop_event = asyncio.Event()

def calculate_step_cost(provider: str, model: str, text: str, usage: Optional[Dict[str, Any]] = None):
    """Builds the {text_analytics, pricing_estimation} cost block for one pipeline step."""
    usage = usage or {}
    return calculator.calculate_cost_and_metrics(
        text=text,
        model_name=model,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
    )


def meta_path(output_file: Path) -> Path:
    return output_file.with_suffix(".meta.json")


def write_step_meta(output_file: Path, metrics: Dict[str, Any], cost: Dict[str, Any]) -> None:
    with open(meta_path(output_file), "w", encoding="utf-8") as f:
        json.dump({"metrics": metrics, "cost": cost}, f)


def read_step_meta(output_file: Path) -> Optional[Dict[str, Any]]:
    meta_file = meta_path(output_file)
    if not meta_file.exists():
        return None
    with open(meta_file, "r", encoding="utf-8") as f:
        return json.load(f)


def empty_phase_telemetry(provider: str = None, model: str = None) -> Dict[str, Any]:
    return {
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "provider": provider,
        "model": model,
        "cost": {"total_cost_usd": "$0.000000", "total_cost_pkr": "Rs. 0.0000"},
    }


@router.get("/api/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "Briefcast API"}



@router.get("/api/settings", tags=["Settings"])
async def get_settings():
    record = get_saved_config()
    if record:
        try:
            return GlobalSettings(**record).model_dump()
        except ValueError:
            defaults = GlobalSettings().model_dump()
            save_config(defaults)
            return defaults
    return GlobalSettings().model_dump()


@router.get("/api/config", tags=["Configuration"])
async def get_public_config():
    return public_config()


@router.post("/api/settings", tags=["Settings"])
async def update_settings(settings: GlobalSettings):
    save_config(settings.model_dump())
    return {"message": "Settings updated successfully"}


def record_datetime(record: Dict[str, Any]) -> Optional[datetime]:
    value = record.get("completed_at") or record.get("timestamp")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace(" ", "T"))
    except ValueError:
        return None


def record_response(record: Dict[str, Any], base_url: str = "") -> Dict[str, Any]:
    base_url = str(base_url).rstrip("/")
    audio_file = record.get("audio_file")
    summary_file = record.get("summary_file")
    translation_file = record.get("translation_file")
    
    return {
        "job_id": record.get("id") or record.get("transaction_id"),
        "filename": record.get("filename"),
        "company_name": record.get("company_name"),
        "symbol": record.get("symbol"),
        "status": record.get("status"),
        "received_at": record.get("received_at") or record.get("timestamp"),
        "completed_at": record.get("completed_at"),
        
        "summary": record.get("english_summary"),
        "summary_file": summary_file,
        "summary_url": f"{base_url}/files/{summary_file}" if summary_file else None,
        
        "translation": record.get("urdu_summary"),
        "translation_file": translation_file,
        "translation_url": f"{base_url}/files/{translation_file}" if translation_file else None,
        
        "audio_file": audio_file,
        "audio_url": f"{base_url}/audio/{audio_file}" if audio_file else None,
        "error": record.get("error"),
    }



def list_directory_files(directory: Path) -> List[Dict[str, Any]]:
    files = []
    for file_path in directory.iterdir():
        if not file_path.is_file() or file_path.name == "briefcast_db.json":
            continue
        stat = file_path.stat()
        files.append(
            {
                "filename": file_path.name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        )
    return sorted(files, key=lambda item: item["modified_at"], reverse=True)


@router.get("/api/dashboard", tags=["Operations"])
async def dashboard_status():
    processing = list(active_jobs.values())
    
    completed = 0
    for _ in PROCESSED_DOCS_DIR.glob(f"*{MANIFEST_FILE_SUFFIX}"):
        completed += 1
        
    failed = 0
    for _ in FAILED_FILES_DIR.glob(f"*{ERROR_FILE_SUFFIX}"):
        failed += 1

    return {
        "scanner": scanner_status(),
        "counts": {
            "processing": len(processing),
            "completed": completed,
            "failed": failed,
            "input_files": len(list_source_files()),
        },
        "processing": processing,
        "input_files": await asyncio.to_thread(list_source_files),
        "processed_files": await asyncio.to_thread(
            list_directory_files, PROCESSED_DOCS_DIR
        ),
        "failed_files": await asyncio.to_thread(
            list_directory_files, FAILED_FILES_DIR
        ),
    }
    
@router.get("/api/logs", tags=["Operations"])
async def get_server_logs(lines: int = 100):
    """Return the last N lines of the server log file."""
    if not LOG_FILE_PATH.exists():
        return {"logs": ["Log file not created yet."]}
    
    try:
        def read_last_lines():
            # A simple approach to read the end of a file
            with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
                content = f.readlines()
                return [line.strip() for line in content[-lines:]]
                
        log_lines = await asyncio.to_thread(read_last_lines)
        return {"logs": log_lines}
    except Exception as e:
        return {"logs": [f"Error reading logs: {e}"]}


@router.post("/api/upload-docs", tags=["Data"])
async def upload_documents(files: List[UploadFile] = File(...)):
    saved_files = []
    for file in files:
        try:
            safe_filename = os.path.basename(file.filename)
            suffix = Path(safe_filename).suffix.lower()
            if suffix not in SUPPORTED_DOCUMENT_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type '{suffix or 'unknown'}'. Use TXT, PDF, or DOCX.",
                )

            destination = INPUT_DOCS_DIR / safe_filename
            if destination.exists() or (PROCESSED_DOCS_DIR / safe_filename).exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                destination = INPUT_DOCS_DIR / f"{Path(safe_filename).stem}_{timestamp}{suffix}"

            temporary = destination.with_suffix(destination.suffix + ".part")
            with open(temporary, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            temporary.replace(destination)
            saved_files.append(destination.name)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {
        "message": f"Successfully uploaded {len(saved_files)} file(s).",
        "filenames": saved_files,
    }


def source_file_status(file_path: Path) -> str:
    base_name = file_path.stem
    # check active jobs first
    for job in active_jobs.values():
        if job.get("filename") == file_path.name:
            return job.get("status", "processing")
            
    if (PROCESSED_DOCS_DIR / f"{base_name}{AUDIO_FILE_SUFFIX}").exists():
        return "completed"
    if (PROCESSED_DOCS_DIR / f"{base_name}{TRANSLATION_FILE_SUFFIX}").exists():
        return "translated"
    if (PROCESSED_DOCS_DIR / f"{base_name}{SUMMARY_FILE_SUFFIX}").exists():
        return "summarized"
    return "ready"


def list_source_files() -> List[Dict[str, Any]]:
    supported = set(SUPPORTED_DOCUMENT_EXTENSIONS)
    files = []
    for file_path in INPUT_DOCS_DIR.iterdir():
        if not file_path.is_file() or file_path.suffix.lower() not in supported:
            continue
        stat = file_path.stat()
        files.append(
            {
                "filename": file_path.name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "status": source_file_status(file_path),
            }
        )
    return sorted(files, key=lambda item: item["modified_at"], reverse=True)


@router.get("/api/source-files", tags=["Document Intake"])
async def get_source_files():
    return {
        "source_directory": str(INPUT_DOCS_DIR),
        "processed_directory": str(PROCESSED_DOCS_DIR),
        "failed_directory": str(FAILED_FILES_DIR),
        "files": await asyncio.to_thread(list_source_files),
    }


@router.post("/api/scanner/scan", tags=["Document Intake"])
async def scan_source_folder():
    files = await asyncio.to_thread(list_source_files)
    return {
        "message": f"Scan complete. Found {len(files)} supported file(s).",
        "files": files,
    }


@router.get("/api/scanner/status", tags=["Document Intake"])
async def get_scanner_status():
    return scanner_status()


@router.post("/api/scanner/start", tags=["Document Intake"])
async def start_scanner_endpoint(config: Optional[Dict[str, Any]] = Body(default=None)):
    if config:
        settings_table.upsert(config, doc_ids=[1])
    try:
        await start_folder_scanner()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return scanner_status()


@router.post("/api/scanner/stop", tags=["Document Intake"])
async def stop_scanner_endpoint():
    await stop_folder_scanner()
    return scanner_status()


# ==========================================
# CORE BACKGROUND PIPELINE & ASSETS
# ==========================================

@router.get("/audio/{filename}", tags=["Data"])
async def get_audio_file(filename: str):
    file_path = PROCESSED_DOCS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    media_type = "audio/mpeg" if file_path.suffix.lower() == ".mp3" else "audio/wav"
    return FileResponse(path=file_path, media_type=media_type, filename=filename)


async def run_pipeline_core(
    transaction_id: str,
    filename: str,
    content: str,
    config: PipelineConfig
) -> dict:
    """Core pipeline execution, returns the completed doc_record dict."""
    base_name = Path(filename).stem
    source_file = INPUT_DOCS_DIR / filename
    audio_filename = f"{base_name}{AUDIO_FILE_SUFFIX}"
    start_time = time.time()
    
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

        logger.info(f"[Pipeline] [{filename}] Executing Agent Graph (Extract -> Summary -> Translate -> Audio)...")
        final_state = await document_graph.ainvoke(initial_state)
        logger.info(f"[Pipeline] [{filename}] Graph execution completed successfully. Calculating costs...")

        summary_metrics = final_state.get("summary_metrics", {})
        translation_metrics = final_state.get("translation_metrics", {})
        audio_metrics = final_state.get("audio_metrics", {})
        extracted_data = summary_metrics.get("extracted_data", {}) or {}
        existing_record = active_jobs.get(transaction_id) or {}

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
        logger.info(f"[Pipeline] [{filename}] Total estimated cost: ${tot_usd:.6f} / Rs. {tot_pkr:.4f}")

        # Save the intermediate text files as requested
        logger.info(f"[Pipeline] [{filename}] Writing generated summary and translation files...")
        with open(PROCESSED_DOCS_DIR / f"{base_name}{SUMMARY_FILE_SUFFIX}", "w", encoding="utf-8") as f:
            f.write(final_state["english_summary"])
            
        with open(PROCESSED_DOCS_DIR / f"{base_name}{TRANSLATION_FILE_SUFFIX}", "w", encoding="utf-8") as f:
            f.write(final_state["urdu_summary"])

        total_time = round(time.time() - start_time, 2)
        
        doc_record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "completed",
            "filename": filename,
            "received_at": existing_record.get("received_at") or existing_record.get("timestamp"),
            "completed_at": datetime.now().isoformat(),
            "company_name": summary_metrics.get("extracted_name") or extracted_data.get("company_name"),
            "symbol": extracted_data.get("symbol"),
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
        active_jobs.pop(transaction_id, None)
        await asyncio.to_thread(finalize_source_file, filename, transaction_id, doc_record)
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
        active_jobs.pop(transaction_id, None)
        await asyncio.to_thread(fail_source_file, filename, transaction_id, str(e))
        return doc_record


async def run_pipeline_background(
    transaction_id: str,
    filename: str,
    content: str,
    config: PipelineConfig,
    webhook_url: str
):
    """Background task to run the core pipeline and fire a webhook."""
    doc_record = await run_pipeline_core(transaction_id, filename, content, config)
    
    if webhook_url and doc_record:
        try:
            def send_webhook():
                requests.post(webhook_url, json=doc_record, timeout=10)
            await asyncio.to_thread(send_webhook)
            logger.info(f"Fired webhook to {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to fire webhook to {webhook_url}: {str(e)}")


def scanner_status() -> Dict[str, Any]:
    running = scanner_task is not None and not scanner_task.done()
    configuration_error = scanner_configuration_error()
    return {
        "running": running,
        "enabled": scanner_runtime_enabled,
        "interval_seconds": SCANNER_INTERVAL_SECONDS,
        "active_files": [scanner_active_file] if scanner_active_file else [],
        "configuration_ready": configuration_error is None,
        "configuration_error": configuration_error,
        "source_directory": str(INPUT_DOCS_DIR),
        "processed_directory": str(PROCESSED_DOCS_DIR),
        "failed_directory": str(FAILED_FILES_DIR),
    }


def scanner_configuration_error() -> Optional[str]:
    if not os.getenv("GEMINI_API_KEY"):
        return "GEMINI_API_KEY is required by the financial extraction pipeline."
    return None


def scanner_fingerprint(file_path: Path) -> str:
    stat = file_path.stat()
    return f"{file_path.name}:{stat.st_size}:{stat.st_mtime_ns}"


def scanner_collision_exists(file_path: Path) -> bool:
    base_name = file_path.stem
    return any(
        path.exists()
        for path in (
            PROCESSED_DOCS_DIR / file_path.name,
            PROCESSED_DOCS_DIR / f"{base_name}{SUMMARY_FILE_SUFFIX}",
            PROCESSED_DOCS_DIR / f"{base_name}{TRANSLATION_FILE_SUFFIX}",
            PROCESSED_DOCS_DIR / f"{base_name}{AUDIO_FILE_SUFFIX}",
        )
    )


def timestamp_source_file(file_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = file_path.with_name(f"{file_path.stem}_{timestamp}{file_path.suffix}")
    counter = 2
    while candidate.exists():
        candidate = file_path.with_name(
            f"{file_path.stem}_{timestamp}_{counter}{file_path.suffix}"
        )
        counter += 1
    file_path.replace(candidate)
    return candidate


async def process_scanner_file(file_path: Path, transaction_id: str) -> None:
    global scanner_active_file
    filename = file_path.name

    scanner_active_file = filename
    try:
        if not file_path.exists():
            logger.warning(f"[Scanner] File {filename} disappeared before it could be processed.")
            return

        processing_path = PROCESSING_DOCS_DIR / filename
        logger.info(f"[Scanner] Moving {filename} to processing folder to prevent duplicate scans.")
        try:
            file_path.rename(processing_path)
            file_path = processing_path
        except Exception as e:
            logger.error(f"[Scanner] Failed to move {filename} to processing folder: {e}")
            return

        logger.info(f"[Scanner] Starting processing for new file: {filename} (Transaction: {transaction_id})")
        if transaction_id in active_jobs:
            active_jobs[transaction_id]["status"] = "processing"
            active_jobs[transaction_id]["started_at"] = datetime.now().isoformat()
            
        try:
            logger.debug(f"[Scanner] Reading content from {filename}...")
            content = await asyncio.to_thread(DocumentService.read_file, file_path)
            if not content.strip():
                raise ValueError(f"No readable text was found in {filename}.")
            logger.info(f"[Scanner] Successfully read {len(content)} characters from {filename}.")
        except Exception as exc:
            logger.error(f"[Scanner] Failed to read {filename}: {exc}")
            if transaction_id in active_jobs:
                active_jobs[transaction_id]["status"] = "error"
                active_jobs[transaction_id]["error"] = str(exc)
                active_jobs[transaction_id]["completed_at"] = datetime.now().isoformat()
            await asyncio.to_thread(
                fail_source_file, filename, transaction_id, str(exc)
            )
            return

        record_cfg = get_saved_config()
        config = PipelineConfig(**(record_cfg or GlobalSettings().model_dump()))
        logger.info(f"[Scanner] Handing {filename} off to the core AI pipeline...")
        await run_pipeline_core(transaction_id, filename, content, config)
    finally:
        scanner_active_file = None


async def scan_input_folder() -> None:
    supported = set(SUPPORTED_DOCUMENT_EXTENSIONS)

    
    files_scanned = 0
    for file_path in sorted(INPUT_DOCS_DIR.iterdir(), key=lambda path: path.name):
        if not file_path.is_file() or file_path.suffix.lower() not in supported:
            continue
        
        files_scanned += 1

        if scanner_collision_exists(file_path):
            logger.info(f"[Scanner] File already processed ({file_path.name}). Removing from input folder.")
            try:
                file_path.unlink()
            except Exception as e:
                logger.error(f"[Scanner] Failed to remove duplicate file {file_path.name}: {e}")
            continue
        fingerprint = scanner_fingerprint(file_path)

        logger.info(f"[Scanner] New unprocessed file discovered: {file_path.name}")
        # Failed or interrupted source files get a fresh attempt while the old
        # audit record remains unchanged.
        transaction_id = str(uuid.uuid4())
        active_jobs[transaction_id] = {
            "id": transaction_id,
            "filename": file_path.name,
            "status": "processing",
            "received_at": datetime.now().isoformat()
        }
        await process_scanner_file(file_path, transaction_id)
        
    if files_scanned == 0:
        logger.debug("[Scanner] Directory scan complete. No files to process.")


async def scanner_loop() -> None:
    while scanner_runtime_enabled:
        try:
            await scan_input_folder()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Folder scanner iteration failed")
        if not scanner_runtime_enabled:
            break
        try:
            await asyncio.wait_for(
                scanner_stop_event.wait(), timeout=SCANNER_INTERVAL_SECONDS
            )
        except TimeoutError:
            pass


async def start_folder_scanner() -> None:
    global scanner_runtime_enabled, scanner_task
    configuration_error = scanner_configuration_error()
    if configuration_error:
        raise RuntimeError(configuration_error)
    scanner_runtime_enabled = True
    scanner_stop_event.clear()
    if scanner_task is None or scanner_task.done():
        scanner_task = asyncio.create_task(scanner_loop(), name="briefcast-folder-scanner")


async def stop_folder_scanner() -> None:
    global scanner_runtime_enabled, scanner_task
    scanner_runtime_enabled = False
    scanner_stop_event.set()
    task = scanner_task
    if task and not task.done() and task is not asyncio.current_task():
        await task
    scanner_task = None


async def shutdown_folder_scanner() -> None:
    """Stop scanning after the current document finishes."""
    await stop_folder_scanner()


def finalize_source_file(filename: str, transaction_id: str, record: dict) -> None:
    source_file = PROCESSING_DOCS_DIR / filename
    destination = PROCESSED_DOCS_DIR / filename
    base_name = Path(filename).stem
    record = record or {}
    manifest = {
        "job_id": transaction_id,
        "original_filename": filename,
        "status": "completed",
        "completed_at": datetime.now().isoformat(),
        "company_name": record.get("company_name"),
        "symbol": record.get("symbol"),
        "summary_file": f"{base_name}{SUMMARY_FILE_SUFFIX}",
        "translation_file": f"{base_name}{TRANSLATION_FILE_SUFFIX}",
        "audio_file": f"{base_name}{AUDIO_FILE_SUFFIX}",
        "english_summary": record.get("english_summary"),
        "urdu_summary": record.get("urdu_summary")
    }
    with open(
        PROCESSED_DOCS_DIR / f"{base_name}{MANIFEST_FILE_SUFFIX}", "w", encoding="utf-8"
    ) as manifest_file:
        json.dump(manifest, manifest_file, ensure_ascii=False, indent=2)
    if source_file.exists():
        source_file.replace(destination)


def fail_source_file(filename: str, transaction_id: str, error: str) -> None:
    source_file = PROCESSING_DOCS_DIR / filename
    base_name = Path(filename).stem
    destination = FAILED_FILES_DIR / filename
    if destination.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = FAILED_FILES_DIR / f"{base_name}_{timestamp}{Path(filename).suffix}"
        base_name = destination.stem
    manifest = {
        "job_id": transaction_id,
        "original_filename": filename,
        "status": "error",
        "failed_at": datetime.now().isoformat(),
        "error": error,
    }
    with open(
        FAILED_FILES_DIR / f"{base_name}{ERROR_FILE_SUFFIX}", "w", encoding="utf-8"
    ) as manifest_file:
        json.dump(manifest, manifest_file, ensure_ascii=False, indent=2)
    if source_file.exists():
        source_file.replace(destination)


# --- Public Integration Endpoints ---

@router.get("/files/{filename}", tags=["Public Integration"])
async def download_file(filename: str):
    """Download a processed file (summary text, translation text)."""
    file_path = PROCESSED_DOCS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "text/plain" if filename.endswith((".txt", ".md")) else "application/octet-stream"
    return FileResponse(path=file_path, media_type=media_type, filename=filename)


async def _get_all_manifests() -> List[Dict[str, Any]]:
    def scan_records():
        records = []
        for manifest_path in PROCESSED_DOCS_DIR.glob(f"*{MANIFEST_FILE_SUFFIX}"):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    records.append(json.load(f))
            except Exception:
                continue
        return records
    records = await asyncio.to_thread(scan_records)
    records.sort(key=lambda r: record_datetime(r) or datetime.min, reverse=True)
    return records


@router.get("/recent", tags=["Public Integration"])
async def get_recent_files(request: Request, limit: int = 10):
    """Get a list of the most recently processed files."""
    records = await _get_all_manifests()
    return {"records": [record_response(r, str(request.base_url)) for r in records[:limit]]}


@router.get("/search/name", tags=["Public Integration"])
async def search_files_by_name(request: Request, query: str):
    """Search processed files by original filename or company name."""
    records = await _get_all_manifests()
    query_lower = query.casefold().strip()
    
    matches = []
    for r in records:
        searchable_text = " ".join(filter(None, [
            r.get("filename"), 
            r.get("original_filename"), 
            r.get("company_name")
        ])).casefold()
        
        if query_lower in searchable_text:
            matches.append(r)
            
    return {"records": [record_response(r, str(request.base_url)) for r in matches]}


@router.get("/search/date", tags=["Public Integration"])
async def search_files_by_date(
    request: Request, 
    start_date: str = ApiQuery(default="today", description="Format YYYY-MM-DD or 'today'"), 
    end_date: str = ApiQuery(default="today", description="Format YYYY-MM-DD or 'today'")
):
    """Search processed files by a date range."""
    if start_date.casefold() == "today":
        start_date = datetime.now().date().isoformat()
    if end_date.casefold() == "today":
        end_date = datetime.now().date().isoformat()
        
    try:
        start_dt = datetime.fromisoformat(start_date).date()
        end_dt = datetime.fromisoformat(end_date).date()
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="start_date and end_date must use YYYY-MM-DD."
        ) from exc

    if start_dt > end_dt:
        raise HTTPException(status_code=400, detail="start_date must be before end_date.")

    records = await _get_all_manifests()
    matches = []
    
    for r in records:
        record_time = record_datetime(r)
        if not record_time:
            continue
        
        record_date = record_time.date()
        if start_dt <= record_date <= end_dt:
            matches.append(r)
            
    return {"records": [record_response(r, str(request.base_url)) for r in matches]}

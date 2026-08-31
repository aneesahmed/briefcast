# src/api/routes.py
import asyncio
import json
import os
import shutil
import uuid
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, File, HTTPException, UploadFile, Body, BackgroundTasks, Query as ApiQuery
from fastapi.responses import FileResponse
import requests
from tinydb import TinyDB, Query

from src.core.config import (
    AUDIO_FILE_SUFFIX,
    AUDIO_MODEL,
    AUDIO_PROVIDER,
    DEFAULT_STAGED_FILENAME,
    ERROR_FILE_SUFFIX,
    FAILED_FILES_DIR,
    INPUT_DOCS_DIR,
    MANIFEST_FILE_SUFFIX,
    PROCESSED_DOCS_DIR,
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

db = TinyDB(PROCESSED_DOCS_DIR / "briefcast_db.json")
settings_table = db.table("settings")

scanner_runtime_enabled = SCANNER_ENABLED
scanner_task: Optional[asyncio.Task] = None
scanner_active_file: Optional[str] = None
scanner_stop_event = asyncio.Event()

def calculate_step_cost(provider: str, model: str, text: str, usage: Optional[Dict[str, Any]] = None):
    """Builds the {text_analytics, pricing_estimation} cost block for one pipeline step.

    Always prefers the real token usage already returned by the LLM call (`usage`)
    over re-deriving it from `text`, so the displayed token count and the cost
    figure next to it are computed from the same numbers.
    """
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
    record = settings_table.get(doc_id=1)
    if record:
        try:
            return GlobalSettings(**record).model_dump()
        except ValueError:
            defaults = GlobalSettings().model_dump()
            settings_table.upsert(defaults, doc_ids=[1])
            return defaults
    return GlobalSettings().model_dump()


@router.get("/api/config", tags=["Configuration"])
async def get_public_config():
    """Return committed, non-secret settings used by both backend and UI."""
    return public_config()


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


def record_datetime(record: Dict[str, Any]) -> Optional[datetime]:
    value = record.get("completed_at") or record.get("timestamp")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace(" ", "T"))
    except ValueError:
        return None


def record_response(record: Dict[str, Any]) -> Dict[str, Any]:
    audio_file = record.get("audio_file")
    return {
        "job_id": record.get("id") or record.get("transaction_id"),
        "filename": record.get("filename"),
        "company_name": record.get("company_name"),
        "symbol": record.get("symbol"),
        "status": record.get("status"),
        "received_at": record.get("received_at") or record.get("timestamp"),
        "completed_at": record.get("completed_at"),
        "summary": record.get("english_summary"),
        "translation": record.get("urdu_summary"),
        "audio_file": audio_file,
        "audio_url": f"/audio/{audio_file}" if audio_file else None,
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


@router.get("/api/dashboard", tags=["Dashboard"])
async def get_dashboard_data():
    records = db.all()
    processing = [
        record_response(record)
        for record in records
        if record.get("status") in {"processing", "in progress"}
    ]
    completed = sum(record.get("status") == "completed" for record in records)
    failed = sum(record.get("status") == "error" for record in records)
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


@router.get("/api/records", tags=["Processed Records"])
async def search_processed_records(
    name: Optional[str] = None,
    symbol: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    last_n_days: Optional[int] = ApiQuery(default=None, ge=1, le=3650),
    status: Optional[str] = None,
):
    try:
        start_date = datetime.fromisoformat(date_from).date() if date_from else None
        end_date = datetime.fromisoformat(date_to).date() if date_to else None
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="date_from and date_to must use YYYY-MM-DD."
        ) from exc

    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="date_from must be before date_to.")

    cutoff = datetime.now() - timedelta(days=last_n_days) if last_n_days else None
    name_query = name.casefold().strip() if name else None
    symbol_query = symbol.casefold().strip() if symbol else None
    status_query = status.casefold().strip() if status else None
    matches = []

    for record in db.all():
        record_time = record_datetime(record)
        if cutoff and (not record_time or record_time < cutoff):
            continue
        if start_date and (not record_time or record_time.date() < start_date):
            continue
        if end_date and (not record_time or record_time.date() > end_date):
            continue
        if status_query and str(record.get("status", "")).casefold() != status_query:
            continue
        if name_query:
            searchable_name = " ".join(
                filter(None, [record.get("filename"), record.get("company_name")])
            ).casefold()
            if name_query not in searchable_name:
                continue
        if symbol_query and symbol_query not in str(record.get("symbol") or "").casefold():
            continue
        matches.append(record)

    matches.sort(key=lambda item: record_datetime(item) or datetime.min, reverse=True)
    return {
        "count": len(matches),
        "filters": {
            "name": name,
            "symbol": symbol,
            "date_from": date_from,
            "date_to": date_to,
            "last_n_days": last_n_days,
            "status": status,
        },
        "records": [record_response(record) for record in matches],
    }


@router.get("/api/records/{job_id}", tags=["Processed Records"])
async def get_processed_record(job_id: str):
    q = Query()
    record = db.get((q.id == job_id) | (q.transaction_id == job_id))
    if not record:
        raise HTTPException(status_code=404, detail="Processed record not found.")
    return record_response(record)


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
    q = Query()
    records = db.search(q.filename == file_path.name)
    if records:
        latest_status = records[-1].get("status")
        if latest_status in {"processing", "in progress", "error"}:
            return "processing" if latest_status == "in progress" else latest_status
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
    output_file = PROCESSED_DOCS_DIR / f"{base_name}{SUMMARY_FILE_SUFFIX}"

    if output_file.exists() and not payload.get("force"):
        with open(output_file, "r", encoding="utf-8") as f:
            english_summary = f.read()
        cached_meta = read_step_meta(output_file) or {}
        return {
            "filename": filename,
            "english_summary": english_summary,
            "metrics": cached_meta.get("metrics"),
            "cost": cached_meta.get("cost"),
            "cached": True,
        }

    if not input_file.exists():
        raise HTTPException(status_code=404, detail=f"Input file {filename} not found.")

    try:
        raw_text = await asyncio.to_thread(DocumentService.read_file, input_file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Could not extract text from {filename}: {exc}"
        ) from exc

    if not raw_text.strip():
        raise HTTPException(
            status_code=422,
            detail=f"No readable text was found in {filename}.",
        )

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

    provider = config.get("summary_provider", SUMMARY_PROVIDER)
    model = config.get("summary_model", SUMMARY_MODEL)
    usage = res["summary_metrics"].get("usage", {})
    cost_info = calculate_step_cost(provider, model, raw_text, usage=usage)
    write_step_meta(output_file, res["summary_metrics"], cost_info)

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
    filename = payload.get("filename", DEFAULT_STAGED_FILENAME)
    english_summary_override = payload.get("english_summary")

    base_name = Path(filename).stem
    input_file = PROCESSED_DOCS_DIR / f"{base_name}{SUMMARY_FILE_SUFFIX}"
    output_file = PROCESSED_DOCS_DIR / f"{base_name}{TRANSLATION_FILE_SUFFIX}"

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
        cached_meta = read_step_meta(output_file) or {}
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

    provider = config.get("translation_provider", TRANSLATION_PROVIDER)
    model = config.get("translation_model", TRANSLATION_MODEL)
    usage = res["translation_metrics"].get("usage", {})
    cost_info = calculate_step_cost(provider, model, english_summary, usage=usage)
    write_step_meta(output_file, res["translation_metrics"], cost_info)

    return {
        "filename": filename,
        "urdu_summary": res["urdu_summary"],
        "metrics": res["translation_metrics"],
        "cost": cost_info,
        "cached": False,
    }


def phase_telemetry_from_meta(
    meta: Optional[Dict[str, Any]], provider: Optional[str], model: Optional[str]
) -> Dict[str, Any]:
    """Builds one telemetry phase entry from a step's persisted {metrics, cost} sidecar."""
    if not meta:
        return empty_phase_telemetry(provider, model)
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


def phase_raw_cost(meta: Optional[Dict[str, Any]]) -> tuple:
    if not meta:
        return 0.0, 0.0
    raw = (meta.get("cost") or {}).get("pricing_estimation", {}).get("raw_values", {})
    return raw.get("total_usd", 0.0), raw.get("total_pkr", 0.0)


def finalize_source_file(filename: str, transaction_id: str) -> None:
    """Move the completed source beside its flat, consistently-prefixed artifacts."""
    source_file = INPUT_DOCS_DIR / filename
    destination = PROCESSED_DOCS_DIR / filename
    base_name = Path(filename).stem
    q = Query()
    record = db.get(q.id == transaction_id) or {}
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
    }
    with open(
        PROCESSED_DOCS_DIR / f"{base_name}{MANIFEST_FILE_SUFFIX}", "w", encoding="utf-8"
    ) as manifest_file:
        json.dump(manifest, manifest_file, ensure_ascii=False, indent=2)
    if source_file.exists():
        source_file.replace(destination)


def fail_source_file(filename: str, transaction_id: str, error: str) -> None:
    """Archive a failed source with a machine-readable error manifest."""
    source_file = INPUT_DOCS_DIR / filename
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


@router.post("/api/step/audio", tags=["React Studio (Step-by-Step)"])
async def step_audio(payload: Dict[str, Any] = Body(...)):
    config = payload.get("config", {})
    filename = payload.get("filename", DEFAULT_STAGED_FILENAME)
    urdu_summary_override = payload.get("urdu_summary")

    base_name = Path(filename).stem
    input_file = PROCESSED_DOCS_DIR / f"{base_name}{TRANSLATION_FILE_SUFFIX}"

    # Stable filename (no per-request uuid) so the cache/force toggle actually works,
    # matching the summary/translation steps. The DB transaction still gets its own id.
    audio_filename = f"{base_name}{AUDIO_FILE_SUFFIX}"
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
        cached_meta = read_step_meta(output_file) or {}
        return {
            "filename": filename,
            "download_url": f"/audio/{audio_filename}",
            "metrics": cached_meta.get("metrics"),
            "cost": cached_meta.get("cost"),
            "cached": True,
        }

    with open(input_file, "r", encoding="utf-8") as f:
        urdu_summary = f.read()

    summary_file = PROCESSED_DOCS_DIR / f"{base_name}{SUMMARY_FILE_SUFFIX}"
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

    audio_provider = config.get("audio_provider", AUDIO_PROVIDER)
    audio_model = config.get("audio_model", AUDIO_MODEL)

    # Audio output tokens are not available from synthesis, so estimate them from
    # source text for the dashboard's cost display.
    approx_output_tokens = len(urdu_summary) // 4
    cost_info = calculate_step_cost(
        audio_provider, audio_model, urdu_summary,
        usage={"output_tokens": approx_output_tokens},
    )
    write_step_meta(output_file, res["audio_metrics"], cost_info)

    # Build the full per-phase telemetry + cumulative cost for the audit record by
    # reading back the summary/translation sidecars written earlier in this pipeline
    # run (rather than trusting transient frontend state, which is lost on reload).
    summary_meta = read_step_meta(summary_file)
    translation_meta = read_step_meta(input_file)

    summary_usd, summary_pkr = phase_raw_cost(summary_meta)
    translation_usd, translation_pkr = phase_raw_cost(translation_meta)
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
        "company_name": (summary_meta or {}).get("metrics", {}).get("extracted_name"),
        "symbol": (
            (summary_meta or {}).get("metrics", {}).get("extracted_data", {}) or {}
        ).get("symbol"),
        "completed_at": datetime.now().isoformat(),
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
            "summary_phase": phase_telemetry_from_meta(
                summary_meta, config.get("summary_provider"), config.get("summary_model")
            ),
            "translation_phase": phase_telemetry_from_meta(
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
    await asyncio.to_thread(finalize_source_file, filename, transaction_id)

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
        extracted_data = summary_metrics.get("extracted_data", {}) or {}
        existing_record = db.get(q.id == transaction_id) or {}

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

        # Save the intermediate text files as requested
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
        db.update(doc_record, q.id == transaction_id)
        await asyncio.to_thread(finalize_source_file, filename, transaction_id)
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
        await asyncio.to_thread(fail_source_file, filename, transaction_id, str(e))
        return db.get(q.id == transaction_id)


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
    q = Query()
    scanner_active_file = filename
    try:
        if not file_path.exists():
            return
        db.update(
            {
                "status": "processing",
                "started_at": datetime.now().isoformat(),
            },
            q.id == transaction_id,
        )
        try:
            content = await asyncio.to_thread(DocumentService.read_file, file_path)
            if not content.strip():
                raise ValueError(f"No readable text was found in {filename}.")
        except Exception as exc:
            db.update(
                {
                    "status": "error",
                    "error": str(exc),
                    "completed_at": datetime.now().isoformat(),
                },
                q.id == transaction_id,
            )
            await asyncio.to_thread(
                fail_source_file, filename, transaction_id, str(exc)
            )
            return

        record_cfg = settings_table.get(doc_id=1)
        config = PipelineConfig(**(record_cfg or GlobalSettings().model_dump()))
        await run_pipeline_core(transaction_id, filename, content, config)
    finally:
        scanner_active_file = None


async def scan_input_folder() -> None:
    supported = set(SUPPORTED_DOCUMENT_EXTENSIONS)
    q = Query()

    for file_path in sorted(INPUT_DOCS_DIR.iterdir(), key=lambda path: path.name):
        if not file_path.is_file() or file_path.suffix.lower() not in supported:
            continue

        if scanner_collision_exists(file_path):
            await asyncio.to_thread(timestamp_source_file, file_path)
            continue

        fingerprint = scanner_fingerprint(file_path)
        matches = db.search(q.file_fingerprint == fingerprint)
        existing = matches[-1] if matches else None
        if existing and existing.get("status") == "completed":
            continue

        # Failed or interrupted source files get a fresh attempt while the old
        # audit record remains unchanged.
        transaction_id = str(uuid.uuid4())
        db.insert(
            {
                "id": transaction_id,
                "transaction_id": transaction_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "processing",
                "filename": file_path.name,
                "file_fingerprint": fingerprint,
                "received_at": datetime.now().isoformat(),
            }
        )
        await process_scanner_file(file_path, transaction_id)


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
        background_tasks.add_task(run_pipeline_background, new_job_id, file_name, content, config, None)
        
        return {
            "job_id": new_job_id,
            "file_name": file_name,
            "status": "in progress",
            "details": "Job started successfully."
        }
    except Exception as e:
        logger.error(f"Error starting get_audio job for {file_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))






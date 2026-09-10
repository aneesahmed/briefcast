import asyncio
import json
import logging
import os
import shutil
import uuid
import time
import psycopg2
import psycopg2.extras
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from src.settings import (
    AUDIO_FILE_SUFFIX,
    FAILED_FILES_DIR,
    INPUT_DOCS_DIR,
    MANIFEST_FILE_SUFFIX,
    PROCESSED_DOCS_DIR,
    SUMMARY_FILE_SUFFIX,
    TRANSLATION_FILE_SUFFIX,
    ERROR_FILE_SUFFIX,
)
from src.core.config import (
    SCANNER_ENABLED,
    SCANNER_INTERVAL_SECONDS,
    SUPPORTED_DOCUMENT_EXTENSIONS,
)
from src.models import PipelineConfig
from src.services.agent_graph import document_graph
from src.services.document_service import DocumentService

logger = logging.getLogger("uvicorn.info")
router = APIRouter()

active_jobs: dict[str, dict[str, Any]] = {}
scanner_runtime_enabled = SCANNER_ENABLED
scanner_task: asyncio.Task | None = None
scanner_active_file: str | None = None
scanner_stop_event = asyncio.Event()
local_timezone = datetime.now().astimezone().tzinfo


@router.get("/api/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "Briefcast API"}


@router.post("/api/upload-docs", tags=["Document Intake"])
async def upload_documents(files: Annotated[list[UploadFile], File()]):
    """Place supported documents in the folder watched by the scanner."""
    saved_files: list[str] = []
    for uploaded_file in files:
        safe_filename = Path(uploaded_file.filename or "").name
        suffix = Path(safe_filename).suffix.lower()
        if not safe_filename or suffix not in SUPPORTED_DOCUMENT_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{suffix or 'unknown'}'. Use TXT, PDF, or DOCX.",
            )

        destination = collision_safe_source_path(safe_filename)
        temporary = destination.with_suffix(destination.suffix + ".part")
        try:
            with temporary.open("wb") as buffer:
                shutil.copyfileobj(uploaded_file.file, buffer)
            temporary.replace(destination)
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="Unable to store document") from exc
        finally:
            await uploaded_file.close()
        saved_files.append(destination.name)

    return {
        "message": f"Successfully uploaded {len(saved_files)} file(s).",
        "filenames": saved_files,
    }


@router.get(
    "/api/scanner/status", 
    tags=["Scanner"],
    summary="Get Scanner Status",
    description="Returns the real-time status of the automatic background folder scanner, including whether it is currently running, configuration status, active files, and directory paths.",
    responses={
        200: {
            "description": "Successful Response",
            "content": {
                "application/json": {
                    "example": {
                        "running": True,
                        "enabled": True,
                        "interval_seconds": 10,
                        "active_files": ["Q2_Earnings_Apple.pdf"],
                        "processing_count": 1,
                        "configuration_ready": True,
                        "configuration_error": None,
                        "source_directory": "C:\\catalyst\\briefing_source",
                        "processed_directory": "C:\\catalyst\\briefing_processed",
                        "failed_directory": "C:\\catalyst\\briefing_failed"
                    }
                }
            }
        }
    }
)
async def get_scanner_status():
    return scanner_status()


@router.post("/api/scanner/start", tags=["Scanner"])
async def start_scanner_endpoint():
    try:
        await start_folder_scanner()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return scanner_status()


@router.post("/api/scanner/stop", tags=["Scanner"])
async def stop_scanner_endpoint():
    await stop_folder_scanner()
    return scanner_status()


@router.post("/api/scanner/scan", tags=["Scanner"])
async def scan_now():
    """Run one immediate scan without changing the recurring scanner state."""
    configuration_error = scanner_configuration_error()
    if configuration_error:
        raise HTTPException(status_code=400, detail=configuration_error)
    await scan_input_folder()
    return scanner_status()


@router.get("/api/audio/by-date", tags=["Consumer Audio"])
async def get_audio_by_date(
    request: Request,
    target_date: Annotated[
        str, Query(alias="date", description="Completion date in YYYY-MM-DD format or 'today'")
    ],
):
    """Return titles and downloadable audio URLs completed on the requested date."""
    if target_date.strip().lower() == "today":
        requested_date = datetime.now(local_timezone).date()
    else:
        try:
            requested_date = date.fromisoformat(target_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="date must use YYYY-MM-DD format or 'today'") from exc

    items = []
    for manifest in await load_completed_manifests():
        completed_at = parse_record_datetime(manifest)
        if completed_at is None or completed_at.date() != requested_date:
            continue

        audio_file = manifest.get("audio_file")
        if not isinstance(audio_file, str):
            continue
        try:
            audio_path = resolve_processed_file(audio_file)
        except HTTPException:
            continue
        if not audio_path.is_file():
            continue

        items.append(
            {
                "title": manifest.get("title") or title_from_filename(
                    manifest.get("original_filename", audio_file)
                ),
                "file_name": manifest.get("original_filename"),
                "symbol": manifest.get("symbol"),
                "company_name": manifest.get("company_name"),
                "audio_url": str(request.url_for("download_audio", filename=audio_file)),
            }
        )

    return {"date": requested_date.isoformat(), "count": len(items), "items": items}


@router.get("/api/audio/{filename}", name="download_audio", tags=["Consumer Audio"])
async def download_audio(filename: str):
    """Download one generated Briefcast MP3."""
    if not filename.endswith(AUDIO_FILE_SUFFIX):
        raise HTTPException(status_code=404, detail="Audio file not found")
    file_path = resolve_processed_file(filename)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(file_path, media_type="audio/mpeg", filename=filename)


def resolve_processed_file(filename: str) -> Path:
    """Resolve a generated filename without allowing traversal outside processed_files."""
    if not filename or Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    directory = PROCESSED_DOCS_DIR.resolve()
    candidate = (directory / filename).resolve()
    if candidate.parent != directory:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return candidate


def collision_safe_source_path(filename: str) -> Path:
    candidate = INPUT_DOCS_DIR / filename
    # Collision renaming disabled to allow reusing processed artifacts
    return candidate


def source_name_in_use(source_file: Path) -> bool:
    return source_file.exists() or processed_artifacts_exist(source_file)


def processed_artifacts_exist(source_file: Path) -> bool:
    base_name = source_file.stem
    return any(
        path.exists()
        for path in (
            PROCESSED_DOCS_DIR / source_file.name,
            PROCESSED_DOCS_DIR / f"{base_name}{SUMMARY_FILE_SUFFIX}",
            PROCESSED_DOCS_DIR / f"{base_name}{TRANSLATION_FILE_SUFFIX}",
            PROCESSED_DOCS_DIR / f"{base_name}{AUDIO_FILE_SUFFIX}",
            PROCESSED_DOCS_DIR / f"{base_name}{MANIFEST_FILE_SUFFIX}",
        )
    )


def rename_colliding_source(source_file: Path) -> Path:
    timestamp = datetime.now(local_timezone).strftime("%Y%m%d_%H%M%S_%f")
    destination = source_file.with_name(
        f"{source_file.stem}_{timestamp}{source_file.suffix}"
    )
    source_file.replace(destination)
    return destination


def title_from_filename(filename: str) -> str:
    title = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    return title or "Briefcast audio"


def scanner_status() -> dict[str, Any]:
    running = scanner_task is not None and not scanner_task.done()
    configuration_error = scanner_configuration_error()
    return {
        "running": running,
        "enabled": scanner_runtime_enabled,
        "interval_seconds": SCANNER_INTERVAL_SECONDS,
        "active_files": [scanner_active_file] if scanner_active_file else [],
        "processing_count": len(active_jobs),
        "configuration_ready": configuration_error is None,
        "configuration_error": configuration_error,
        "source_directory": str(INPUT_DOCS_DIR),
        "processed_directory": str(PROCESSED_DOCS_DIR),
        "failed_directory": str(FAILED_FILES_DIR),
    }


def scanner_configuration_error() -> str | None:
    if not os.getenv("GEMINI_API_KEY"):
        return "GEMINI_API_KEY is required to generate summaries, translations, and audio."
    return None


def is_file_locked(filepath: Path) -> bool:
    """Checks if a file is locked by attempting to open it for appending."""
    try:
        with open(filepath, 'a'):
            pass
        return False
    except IOError:
        return True

async def scan_input_folder(stop_when_paused: bool = False) -> None:
    supported = set(SUPPORTED_DOCUMENT_EXTENSIONS)
    source_dir = Path(INPUT_DOCS_DIR)
    source_files = sorted(source_dir.iterdir(), key=lambda path: path.name.casefold())
    
    valid_files = [f for f in source_files if f.is_file() and f.suffix.lower() in supported]
    
    try:
        from zoneinfo import ZoneInfo
        local_timezone = ZoneInfo("Asia/Karachi")
    except ImportError:
        local_timezone = None

    if not valid_files:
        timestamp = datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[{timestamp}] Scanner checked folder: No files to process.")
        return

    for source_file in valid_files:
        if stop_when_paused and not scanner_runtime_enabled:
            break

        if is_file_locked(source_file):
            logger.warning(f"File {source_file.name} is currently locked by another process (likely downloading). Leaving for next scan.")
            continue

        # Collision renaming removed as per user request.
        # We will reuse existing artifacts or regenerate missing ones in-place.

        transaction_id = str(uuid.uuid4())
        
        # Move to processing folder for intermediate processing
        from src.settings import PROCESSING_DOCS_DIR
        processing_file = Path(PROCESSING_DOCS_DIR) / source_file.name
        
        # Now safe to move since we checked for locks
        source_file.replace(processing_file)
        
        active_jobs[transaction_id] = {
            "id": transaction_id,
            "filename": processing_file.name,
            "status": "processing",
            "received_at": datetime.now(local_timezone).isoformat(),
        }
        
        start_time = time.time()
        await process_scanner_file(processing_file, transaction_id)
        elapsed = time.time() - start_time
        
        timestamp = datetime.now(local_timezone).strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Processed file: {source_file.name} at {timestamp} - Time taken: {elapsed:.2f} seconds")


async def process_scanner_file(source_file: Path, transaction_id: str) -> None:
    global scanner_active_file

    scanner_active_file = source_file.name
    try:
        content, ocr_usage, document_type = await asyncio.to_thread(DocumentService.read_file, source_file)
        if not content.strip():
            raise ValueError(f"No readable text was found in {source_file.name}.")
            
        config = PipelineConfig()
        
        file_size_bytes = source_file.stat().st_size if source_file.exists() else 0
        
        await run_pipeline_core(
            transaction_id, 
            source_file.name, 
            content, 
            config, 
            ocr_usage=ocr_usage,
            document_type=document_type,
            file_size_bytes=file_size_bytes
        )
    except Exception as exc:
        logger.exception("Unable to process %s", source_file.name)
        await asyncio.to_thread(fail_source_file, source_file.name, transaction_id, str(exc))
        active_jobs.pop(transaction_id, None)
    finally:
        scanner_active_file = None


async def run_pipeline_core(
    transaction_id: str,
    filename: str,
    content: str,
    config: PipelineConfig,
    ocr_usage: dict[str, int] = None,
    document_type: str = "unknown",
    file_size_bytes: int = 0,
) -> dict[str, Any]:
    base_name = Path(filename).stem
    audio_file = f"{base_name}{AUDIO_FILE_SUFFIX}"
    audio_temporary = f".{base_name}_{transaction_id}.audio.part"
    summary_file = f"{base_name}{SUMMARY_FILE_SUFFIX}"
    translation_file = f"{base_name}{TRANSLATION_FILE_SUFFIX}"

    if ocr_usage is None:
        ocr_usage = {"input_tokens": 0, "output_tokens": 0}

    try:
        final_state = await document_graph.ainvoke(
            {
                "raw_text": content,
                "filename": filename,
                "output_dir": PROCESSED_DOCS_DIR,
                "english_summary": (Path(PROCESSED_DOCS_DIR) / summary_file).read_text(encoding="utf-8") if (Path(PROCESSED_DOCS_DIR) / summary_file).exists() else "",
                "urdu_summary": (Path(PROCESSED_DOCS_DIR) / translation_file).read_text(encoding="utf-8") if (Path(PROCESSED_DOCS_DIR) / translation_file).exists() else "",
                "audio_path": audio_file if (Path(PROCESSED_DOCS_DIR) / audio_file).exists() else audio_temporary,
                "pipeline_config": config.model_dump(),
                "ocr_metrics": ocr_usage,
                "summary_metrics": {},
                "translation_metrics": {},
                "audio_metrics": {},
            }
        )

        summary = final_state["english_summary"].strip()
        translation = final_state["urdu_summary"].strip()
        metrics = final_state.get("summary_metrics", {})
        extracted_data = metrics.get("extracted_data", {}) or {}
        company_name = metrics.get("extracted_name") or extracted_data.get("company_name")
        extracted_title = metrics.get("extracted_title") or extracted_data.get("title")
        title = extracted_title or company_name or title_from_filename(filename)
        callname = final_state.get("callname", "")

        processed_dir = Path(PROCESSED_DOCS_DIR)
        write_text_atomic(processed_dir / summary_file, summary)
        write_text_atomic(processed_dir / translation_file, translation)
        if (processed_dir / audio_temporary).exists():
            (processed_dir / audio_temporary).replace(processed_dir / audio_file)

        from src.core.config import PROCESSING_DOCS_DIR
        source_file_path = Path(PROCESSING_DOCS_DIR) / filename
        if source_file_path.exists():
            source_date = datetime.fromtimestamp(source_file_path.stat().st_mtime, local_timezone).strftime("%Y-%m-%d")
        else:
            source_date = datetime.now(local_timezone).strftime("%Y-%m-%d")

        def get_artifact_size(f_name: str) -> int:
            p = processed_dir / f_name
            return p.stat().st_size if p.exists() else 0

        import json
        try:
            with open("model_pricing.json", "r") as f:
                pricing = json.load(f)
        except Exception:
            pricing = {}

        def compute_cost_cents(metrics: dict, default_model: str = "") -> float:
            if not metrics: return 0.0
            model = metrics.get("model", default_model)
            inp = metrics.get("input_tokens", 0)
            out = metrics.get("output_tokens", 0)
            price = pricing.get(model)
            if price:
                cost_usd = (inp / 1_000_000) * price["input_cost_per_million"] + (out / 1_000_000) * price["output_cost_per_million"]
                return round(cost_usd * 100, 4)
            return 0.0

        ocr_m = final_state.get("ocr_metrics", {})
        ocr_m["cost_cents"] = compute_cost_cents(ocr_m, "gemini-3.7-flash")
        
        sum_m = final_state.get("summary_metrics", {})
        sum_m["cost_cents"] = compute_cost_cents(sum_m, "gemini-3.7-flash")
        
        tra_m = final_state.get("translation_metrics", {})
        tra_m["cost_cents"] = compute_cost_cents(tra_m, "gemini-3.7-flash")
        
        aud_m = final_state.get("audio_metrics", {})
        aud_m["cost_cents"] = compute_cost_cents(aud_m, "gemini-2.5-flash-preview-tts")

        total_cost_cents = round(ocr_m["cost_cents"] + sum_m["cost_cents"] + tra_m["cost_cents"] + aud_m["cost_cents"], 4)
        
        if "english_summary_draft" in extracted_data:
            del extracted_data["english_summary_draft"]

        record = {
            "job_id": transaction_id,
            "original_filename": filename,
            "document_type": document_type,
            "ocr_size_bytes": file_size_bytes,
            "title": title,
            "status": "completed",
            "source_file_date": source_date,
            "completed_at": datetime.now(local_timezone).isoformat(),
            "company_name": company_name,
            "symbol": extracted_data.get("symbol"),
            "calling_name": callname,
            "summary_file": summary_file,
            "summary_size_bytes": get_artifact_size(summary_file),
            "summary_length_words": len(summary.split()),
            "translation_file": translation_file,
            "translation_size_bytes": get_artifact_size(translation_file),
            "translation_length_words": len(translation.split()),
            "audio_file": audio_file,
            "audio_size_bytes": get_artifact_size(audio_file),
            "thinking_level": "LOW",
            "total_cost_cents": total_cost_cents,
            "ocr_metrics": ocr_m,
            "summary_metrics": sum_m,
            "translation_metrics": tra_m,
            "audio_metrics": aud_m,
        }
        await asyncio.to_thread(finalize_source_file, filename, record)
        active_jobs.pop(transaction_id, None)
        logger.info("Successfully processed %s", filename)
        return record
    except Exception as exc:
        remove_generated_artifacts(base_name, audio_temporary)
        await asyncio.to_thread(fail_source_file, filename, transaction_id, str(exc))
        active_jobs.pop(transaction_id, None)
        logger.exception("Error processing %s", filename)
        return {"job_id": transaction_id, "filename": filename, "status": "error", "error": str(exc)}


def write_text_atomic(destination: Path, text: str) -> None:
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(destination)


def remove_generated_artifacts(base_name: str, audio_temporary: str) -> None:
    for path in (
        PROCESSED_DOCS_DIR / audio_temporary,
        PROCESSED_DOCS_DIR / f"{base_name}{SUMMARY_FILE_SUFFIX}",
        PROCESSED_DOCS_DIR / f"{base_name}{TRANSLATION_FILE_SUFFIX}",
        PROCESSED_DOCS_DIR / f"{base_name}{AUDIO_FILE_SUFFIX}",
        PROCESSED_DOCS_DIR / f"{base_name}{MANIFEST_FILE_SUFFIX}",
        PROCESSED_DOCS_DIR / f"{base_name}{MANIFEST_FILE_SUFFIX}.part",
    ):
        path.unlink(missing_ok=True)


def finalize_source_file(filename: str, record: dict[str, Any]) -> None:
    from src.core.config import PROCESSING_DOCS_DIR
    source_file = Path(PROCESSING_DOCS_DIR) / filename
    manifest_file = PROCESSED_DOCS_DIR / f"{Path(filename).stem}{MANIFEST_FILE_SUFFIX}"
    temporary_manifest = manifest_file.with_suffix(manifest_file.suffix + ".part")
    temporary_manifest.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_manifest.replace(manifest_file)
    if source_file.exists():
        source_file.replace(PROCESSED_DOCS_DIR / filename)


def fail_source_file(filename: str, transaction_id: str, error: str) -> None:
    from src.core.config import PROCESSING_DOCS_DIR
    source_file = Path(PROCESSING_DOCS_DIR) / filename
    destination = FAILED_FILES_DIR / filename
    if destination.exists():
        timestamp = datetime.now(local_timezone).strftime("%Y%m%d_%H%M%S_%f")
        destination = destination.with_name(
            f"{destination.stem}_{timestamp}{destination.suffix}"
        )
    error_record = {
        "job_id": transaction_id,
        "original_filename": filename,
        "status": "error",
        "failed_at": datetime.now(local_timezone).isoformat(),
        "error": error,
    }
    error_file = FAILED_FILES_DIR / f"{destination.stem}{ERROR_FILE_SUFFIX}"
    error_file.write_text(
        json.dumps(error_record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if source_file.exists():
        source_file.replace(destination)


def parse_record_datetime(record: dict[str, Any]) -> datetime | None:
    # Prefer completed_at (json creation time) over source_file_date as requested by user
    value = record.get("completed_at") or record.get("source_file_date")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=local_timezone)
        return parsed
    except ValueError:
        return None


async def load_completed_manifests() -> list[dict[str, Any]]:
    def read_manifests() -> list[dict[str, Any]]:
        records = []
        for manifest_path in PROCESSED_DOCS_DIR.glob(f"*{MANIFEST_FILE_SUFFIX}"):
            try:
                records.append(json.loads(manifest_path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                logger.warning("Ignoring unreadable manifest %s", manifest_path.name)
        earliest = datetime.min.replace(tzinfo=local_timezone)
        records.sort(key=lambda item: parse_record_datetime(item) or earliest, reverse=True)
        return records

    return await asyncio.to_thread(read_manifests)


async def scanner_loop() -> None:
    while scanner_runtime_enabled:
        try:
            await scan_input_folder(stop_when_paused=True)
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

audit_scanner_task: asyncio.Task | None = None
audit_scanner_stop_event = asyncio.Event()

def _run_audit_scan():
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres"),
            dbname=os.getenv("DB_NAME", "postgres"),
            port=os.getenv("DB_PORT", "5432"),
        )
        conn.autocommit = True
    except Exception as e:
        logger.error(f"Audit scanner failed to connect to DB: {e}")
        return

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT model_name, input_cost_per_million, output_cost_per_million FROM model_pricing")
            pricing = {row['model_name']: row for row in cur.fetchall()}
            
            manifests = Path(PROCESSED_DOCS_DIR).glob(f"*{MANIFEST_FILE_SUFFIX}")
            for manifest_path in manifests:
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                    
                    filename = manifest.get("original_filename")
                    if not filename:
                        continue
                    
                    cur.execute("SELECT 1 FROM audit_records WHERE filename = %s", (filename,))
                    if cur.fetchone():
                        continue
                    
                    completed_at = manifest.get("completed_at")
                    company_name = manifest.get("company_name", "")
                    symbol = manifest.get("symbol", "")
                    
                    def get_size_mb(fname):
                        p = Path(PROCESSED_DOCS_DIR) / fname if fname else None
                        if p and p.exists():
                            return p.stat().st_size / (1024 * 1024)
                        return 0.0

                    base_name = Path(filename).stem
                    ocr_size_mb = get_size_mb(filename)
                    summary_file = manifest.get("summary_file", f"{base_name}{SUMMARY_FILE_SUFFIX}")
                    summary_size_mb = get_size_mb(summary_file)
                    translation_file = manifest.get("translation_file", f"{base_name}{TRANSLATION_FILE_SUFFIX}")
                    translation_size_mb = get_size_mb(translation_file)
                    audio_file = manifest.get("audio_file", f"{base_name}{AUDIO_FILE_SUFFIX}")
                    audio_size_mb = get_size_mb(audio_file)
                        
                    en_text = manifest.get("english_summary", "")
                    ur_text = manifest.get("urdu_summary", "")
                    
                    def get_total_tokens(metrics_key):
                        metrics = manifest.get(metrics_key, {})
                        if not isinstance(metrics, dict):
                            return 0
                        return metrics.get("input_tokens", 0) + metrics.get("output_tokens", 0)

                    ocr_tokens = get_total_tokens("ocr_metrics")
                    summary_tokens = get_total_tokens("summary_metrics")
                    translation_tokens = get_total_tokens("translation_metrics")
                    
                    audio_metrics = manifest.get("audio_metrics", {})
                    audio_tokens = audio_metrics.get("input_tokens", 0) if isinstance(audio_metrics, dict) else 0
                    
                    model_name = "gemini-3.7-flash"
                    
                    def get_cost(tokens, m_name):
                        if not tokens:
                            return 0.0
                        if m_name in pricing:
                            in_price = pricing[m_name]['input_cost_per_million']
                            out_price = pricing[m_name]['output_cost_per_million']
                            avg_price = (in_price + out_price) / 2
                            return (tokens / 1000000.0) * float(avg_price)
                        return (tokens / 1000000.0) * 0.1875
                        
                    ocr_cost_usd = get_cost(ocr_tokens, model_name)
                    summary_cost_usd = get_cost(summary_tokens, model_name)
                    translation_cost_usd = get_cost(translation_tokens, model_name)
                    audio_cost_usd = get_cost(audio_tokens, model_name)
                        
                    cur.execute("""
                        INSERT INTO audit_records (
                            filename, symbol, company_name, completed_at, model_name,
                            ocr_size_mb, ocr_tokens, ocr_cost_usd,
                            summary_size_mb, summary_tokens, summary_cost_usd,
                            translation_size_mb, translation_tokens, translation_cost_usd,
                            audio_size_mb, audio_tokens, audio_cost_usd
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (filename) DO NOTHING
                    """, (
                        filename, symbol, company_name, completed_at, model_name,
                        ocr_size_mb, ocr_tokens, ocr_cost_usd,
                        summary_size_mb, summary_tokens, summary_cost_usd,
                        translation_size_mb, translation_tokens, translation_cost_usd,
                        audio_size_mb, audio_tokens, audio_cost_usd
                    ))
                except Exception as e:
                    logger.error(f"Error processing manifest {manifest_path.name}: {e}")
    finally:
        conn.close()

async def audit_scanner_loop():
    while not audit_scanner_stop_event.is_set():
        try:
            await asyncio.to_thread(_run_audit_scan)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Audit scanner iteration failed")
        
        try:
            await asyncio.wait_for(audit_scanner_stop_event.wait(), timeout=10)
        except TimeoutError:
            pass

async def start_audit_scanner() -> None:
    global audit_scanner_task
    audit_scanner_stop_event.clear()
    if audit_scanner_task is None or audit_scanner_task.done():
        audit_scanner_task = asyncio.create_task(audit_scanner_loop(), name="briefcast-audit-scanner")

async def stop_audit_scanner() -> None:
    global audit_scanner_task
    audit_scanner_stop_event.set()
    task = audit_scanner_task
    if task and not task.done() and task is not asyncio.current_task():
        await task
    audit_scanner_task = None

@router.get("/api/audit/records", tags=["Audit"])
async def get_audit_records():
    def fetch_records():
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres"),
            dbname=os.getenv("DB_NAME", "postgres"),
            port=os.getenv("DB_PORT", "5432"),
        )
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM audit_records ORDER BY completed_at DESC")
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    return await asyncio.to_thread(fetch_records)

@router.get("/api/audit/daily", tags=["Audit"])
async def get_audit_daily():
    def fetch_daily():
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres"),
            dbname=os.getenv("DB_NAME", "postgres"),
            port=os.getenv("DB_PORT", "5432"),
        )
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM audit_daily_summary ORDER BY audit_date DESC")
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    return await asyncio.to_thread(fetch_daily)

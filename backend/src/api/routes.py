import asyncio
import json
import logging
import os
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from src.core.config import (
    AUDIO_FILE_SUFFIX,
    ERROR_FILE_SUFFIX,
    FAILED_FILES_DIR,
    INPUT_DOCS_DIR,
    MANIFEST_FILE_SUFFIX,
    PROCESSED_DOCS_DIR,
    SCANNER_ENABLED,
    SCANNER_INTERVAL_SECONDS,
    SUMMARY_FILE_SUFFIX,
    SUPPORTED_DOCUMENT_EXTENSIONS,
    TRANSLATION_FILE_SUFFIX,
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


@router.get("/api/scanner/status", tags=["Scanner"])
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
        str, Query(alias="date", description="Completion date in YYYY-MM-DD format")
    ],
):
    """Return titles and downloadable audio URLs completed on the requested date."""
    try:
        requested_date = date.fromisoformat(target_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="date must use YYYY-MM-DD format") from exc

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
    if not source_name_in_use(candidate):
        return candidate

    timestamp = datetime.now(local_timezone).strftime("%Y%m%d_%H%M%S_%f")
    return candidate.with_name(f"{candidate.stem}_{timestamp}{candidate.suffix}")


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


async def scan_input_folder(stop_when_paused: bool = False) -> None:
    supported = set(SUPPORTED_DOCUMENT_EXTENSIONS)
    source_files = sorted(INPUT_DOCS_DIR.iterdir(), key=lambda path: path.name.casefold())
    for source_file in source_files:
        if stop_when_paused and not scanner_runtime_enabled:
            break
        if not source_file.is_file() or source_file.suffix.lower() not in supported:
            continue

        if processed_artifacts_exist(source_file):
            source_file = rename_colliding_source(source_file)

        transaction_id = str(uuid.uuid4())
        active_jobs[transaction_id] = {
            "id": transaction_id,
            "filename": source_file.name,
            "status": "processing",
            "received_at": datetime.now(local_timezone).isoformat(),
        }
        await process_scanner_file(source_file, transaction_id)


async def process_scanner_file(source_file: Path, transaction_id: str) -> None:
    global scanner_active_file

    scanner_active_file = source_file.name
    try:
        content = await asyncio.to_thread(DocumentService.read_file, source_file)
        if not content.strip():
            raise ValueError(f"No readable text was found in {source_file.name}.")
        await run_pipeline_core(transaction_id, source_file.name, content, PipelineConfig())
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
) -> dict[str, Any]:
    base_name = Path(filename).stem
    audio_file = f"{base_name}{AUDIO_FILE_SUFFIX}"
    audio_temporary = f".{base_name}_{transaction_id}.audio.part"
    summary_file = f"{base_name}{SUMMARY_FILE_SUFFIX}"
    translation_file = f"{base_name}{TRANSLATION_FILE_SUFFIX}"

    try:
        final_state = await document_graph.ainvoke(
            {
                "raw_text": content,
                "filename": filename,
                "output_dir": PROCESSED_DOCS_DIR,
                "english_summary": "",
                "urdu_summary": "",
                "audio_path": audio_temporary,
                "pipeline_config": config.model_dump(),
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
        title = company_name or title_from_filename(filename)

        write_text_atomic(PROCESSED_DOCS_DIR / summary_file, summary)
        write_text_atomic(PROCESSED_DOCS_DIR / translation_file, translation)
        (PROCESSED_DOCS_DIR / audio_temporary).replace(PROCESSED_DOCS_DIR / audio_file)

        record = {
            "job_id": transaction_id,
            "original_filename": filename,
            "title": title,
            "status": "completed",
            "completed_at": datetime.now(local_timezone).isoformat(),
            "company_name": company_name,
            "symbol": extracted_data.get("symbol"),
            "summary_file": summary_file,
            "translation_file": translation_file,
            "audio_file": audio_file,
            "english_summary": summary,
            "urdu_summary": translation,
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
    source_file = INPUT_DOCS_DIR / filename
    manifest_file = PROCESSED_DOCS_DIR / f"{Path(filename).stem}{MANIFEST_FILE_SUFFIX}"
    temporary_manifest = manifest_file.with_suffix(manifest_file.suffix + ".part")
    temporary_manifest.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_manifest.replace(manifest_file)
    if source_file.exists():
        source_file.replace(PROCESSED_DOCS_DIR / filename)


def fail_source_file(filename: str, transaction_id: str, error: str) -> None:
    source_file = INPUT_DOCS_DIR / filename
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
    value = record.get("completed_at")
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

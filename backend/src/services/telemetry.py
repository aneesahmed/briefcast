import asyncio
import json
import logging
import sqlite3
from pathlib import Path

from src.core.config import MP3_BIT_RATE_KBPS
from src.services.pricing import (
    MODEL_PRICING_USD_PER_MILLION,
    calculate_cost_usd,
    estimate_audio_output_tokens,
)
from src.settings import AUDIO_MODEL, PROCESSED_DOCS_DIR

logger = logging.getLogger("uvicorn.info")

PROJECT_ROOT = PROCESSED_DOCS_DIR.parent
DB_DIR = PROJECT_ROOT / "db-init"
DB_PATH = DB_DIR / "audit.db"

telemetry_task = None
telemetry_stop_event = asyncio.Event()


def _total_tokens(metrics: object) -> int:
    if not isinstance(metrics, dict):
        return 0
    return sum(
        int(metrics.get(key) or 0)
        for key in ("input_tokens", "output_tokens", "thinking_tokens")
    )


def _metrics_cost(metrics: object, default_model: str) -> float:
    return calculate_cost_usd(metrics if isinstance(metrics, dict) else {}, default_model)

def get_db():
    # Ensure db directory exists
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def ensure_database_schema(conn: sqlite3.Connection) -> None:
    """Create or migrate the audit schema without external SQL files."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS model_pricing (
            model_name TEXT PRIMARY KEY,
            input_cost_per_million REAL NOT NULL,
            output_cost_per_million REAL NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for model_name, rates in MODEL_PRICING_USD_PER_MILLION.items():
        conn.execute(
            """
            INSERT INTO model_pricing (
                model_name, input_cost_per_million, output_cost_per_million
            ) VALUES (?, ?, ?)
            ON CONFLICT(model_name) DO UPDATE SET
                input_cost_per_million=excluded.input_cost_per_million,
                output_cost_per_million=excluded.output_cost_per_million,
                updated_at=CURRENT_TIMESTAMP
            """,
            (model_name, rates["input"], rates["output"]),
        )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_records (
            filename TEXT PRIMARY KEY,
            symbol TEXT,
            company_name TEXT,
            completed_at TIMESTAMP NOT NULL,
            ocr_size_mb REAL DEFAULT 0,
            ocr_tokens INTEGER DEFAULT 0,
            ocr_cost_usd REAL DEFAULT 0,
            summary_size_mb REAL DEFAULT 0,
            summary_tokens INTEGER DEFAULT 0,
            summary_cost_usd REAL DEFAULT 0,
            translation_size_mb REAL DEFAULT 0,
            translation_tokens INTEGER DEFAULT 0,
            translation_cost_usd REAL DEFAULT 0,
            audio_size_mb REAL DEFAULT 0,
            audio_tokens INTEGER DEFAULT 0,
            audio_cost_usd REAL DEFAULT 0,
            audio_duration_seconds REAL DEFAULT 0,
            net_size_mb REAL GENERATED ALWAYS AS (
                ocr_size_mb + summary_size_mb + translation_size_mb + audio_size_mb
            ) STORED,
            net_tokens INTEGER GENERATED ALWAYS AS (
                ocr_tokens + summary_tokens + translation_tokens + audio_tokens
            ) STORED,
            net_cost_usd REAL GENERATED ALWAYS AS (
                ocr_cost_usd + summary_cost_usd + translation_cost_usd + audio_cost_usd
            ) STORED,
            model_name TEXT,
            scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    columns = {
        row[1] for row in conn.execute("PRAGMA table_xinfo(audit_records)").fetchall()
    }
    if "audio_duration_seconds" not in columns:
        conn.execute(
            "ALTER TABLE audit_records ADD COLUMN "
            "audio_duration_seconds REAL DEFAULT 0"
        )

    conn.execute("DROP VIEW IF EXISTS audit_daily_summary")
    conn.execute(
        """
        CREATE VIEW audit_daily_summary AS
        SELECT
            SUBSTR(completed_at, 1, 10) AS audit_date,
            COUNT(filename) AS total_files,
            SUM(ocr_size_mb) AS total_ocr_size_mb,
            SUM(ocr_tokens) AS total_ocr_tokens,
            SUM(ocr_cost_usd) AS total_ocr_cost_usd,
            SUM(summary_size_mb) AS total_summary_size_mb,
            SUM(summary_tokens) AS total_summary_tokens,
            SUM(summary_cost_usd) AS total_summary_cost_usd,
            SUM(translation_size_mb) AS total_translation_size_mb,
            SUM(translation_tokens) AS total_translation_tokens,
            SUM(translation_cost_usd) AS total_translation_cost_usd,
            SUM(audio_size_mb) AS total_audio_size_mb,
            SUM(audio_tokens) AS total_audio_tokens,
            SUM(audio_cost_usd) AS total_audio_cost_usd,
            SUM(net_size_mb) AS total_net_size_mb,
            SUM(net_tokens) AS total_net_tokens,
            SUM(net_cost_usd) AS total_net_cost_usd
        FROM audit_records
        GROUP BY SUBSTR(completed_at, 1, 10)
        ORDER BY audit_date DESC
        """
    )

    schema_exists = conn.execute(
        "SELECT 1 FROM sqlite_master "
        "WHERE type='table' AND name='audit_records'"
    ).fetchone()
    if schema_exists is None:
        raise RuntimeError("audit_records table was not created")


def init_db() -> None:
    """Create the database and fail startup if its schema cannot be initialized."""
    conn = get_db()
    try:
        ensure_database_schema(conn)
        conn.commit()
        logger.info("Audit database ready: %s", DB_PATH)
    except Exception:
        conn.rollback()
        logger.exception("Failed to initialize the audit database")
        raise
    finally:
        conn.close()

def _run_scan():
    conn = get_db()
    try:
        cur = conn.cursor()
        manifests = list(PROCESSED_DOCS_DIR.glob("*_manifest.json"))
        
        new_records = 0
        for manifest_path in manifests:
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                    
                filename = manifest.get("original_filename")
                if not filename:
                    continue
                manifest_completed_at = manifest.get("completed_at")
                if not manifest_completed_at:
                    continue

                company_name = manifest.get("company_name", "")
                symbol = manifest.get("symbol", "")

                def get_size_mb(fname):
                    p = PROCESSED_DOCS_DIR / fname if fname else None
                    if p and p.exists():
                        return p.stat().st_size / (1024 * 1024)
                    return 0.0

                base_name = Path(filename).stem
                ocr_size_mb = manifest.get("ocr_size_bytes", 0) / (1024 * 1024)
                summary_file = manifest.get("summary_file", f"{base_name}_summary.txt")
                summary_size_mb = get_size_mb(summary_file)
                translation_file = manifest.get("translation_file", f"{base_name}_translation.txt")
                translation_size_mb = get_size_mb(translation_file)
                audio_file = manifest.get("audio_file", f"{base_name}_audio.mp3")
                audio_size_mb = get_size_mb(audio_file)

                audio_metrics = manifest.get("audio_metrics", {})
                audio_metrics = dict(audio_metrics) if isinstance(audio_metrics, dict) else {}
                audio_model = str(audio_metrics.get("model") or AUDIO_MODEL)
                audio_metrics["model"] = audio_model

                duration_seconds = manifest.get("audio_duration_seconds")
                if duration_seconds is None:
                    try:
                        audio_path = PROCESSED_DOCS_DIR / audio_file
                        if audio_path.exists():
                            from mutagen.mp3 import MP3
                            audio_obj = MP3(str(audio_path))
                            duration_seconds = round(audio_obj.info.length, 2)
                    except Exception:
                        pass
                
                # If mutagen fails or file missing, fallback to bitrate math
                if not duration_seconds and audio_size_mb > 0:
                    duration_seconds = (
                        audio_size_mb * 1024 * 1024 * 8 / (MP3_BIT_RATE_KBPS * 1000)
                    )

                if not audio_metrics.get("output_tokens") and duration_seconds:
                    audio_metrics["output_tokens"] = estimate_audio_output_tokens(
                        duration_seconds, audio_model
                    )
                    audio_metrics["output_tokens_estimated"] = True

                if not audio_metrics.get("input_tokens") and translation_file:
                    translation_path = PROCESSED_DOCS_DIR / translation_file
                    if translation_path.exists():
                        audio_metrics["input_tokens"] = len(
                            translation_path.read_text(encoding="utf-8")
                        )
                        audio_metrics["input_tokens_estimated"] = True
                
                ocr_metrics = manifest.get("ocr_metrics", {})
                summary_metrics = manifest.get("summary_metrics", {})
                translation_metrics = manifest.get("translation_metrics", {})

                ocr_tokens = _total_tokens(ocr_metrics)
                summary_tokens = _total_tokens(summary_metrics)
                translation_tokens = _total_tokens(translation_metrics)

                audio_tokens = _total_tokens(audio_metrics)
                summary_model = (
                    summary_metrics.get("model")
                    if isinstance(summary_metrics, dict)
                    else None
                )
                model_name = str(summary_model or "gemini-3.7-flash")

                ocr_cost_usd = _metrics_cost(ocr_metrics, "gemini-3.7-flash")
                summary_cost_usd = _metrics_cost(summary_metrics, "gemini-3.7-flash")
                translation_cost_usd = _metrics_cost(
                    translation_metrics, "gemini-3.7-flash"
                )
                audio_cost_usd = _metrics_cost(audio_metrics, AUDIO_MODEL)

                record_values = (
                    filename, symbol, company_name, manifest_completed_at, model_name,
                    ocr_size_mb, ocr_tokens, ocr_cost_usd,
                    summary_size_mb, summary_tokens, summary_cost_usd,
                    translation_size_mb, translation_tokens, translation_cost_usd,
                    audio_size_mb, audio_tokens, audio_cost_usd,
                    duration_seconds or 0.0,
                )
                existing = cur.execute("""
                    SELECT filename, symbol, company_name, completed_at, model_name,
                           ocr_size_mb, ocr_tokens, ocr_cost_usd,
                           summary_size_mb, summary_tokens, summary_cost_usd,
                           translation_size_mb, translation_tokens, translation_cost_usd,
                           audio_size_mb, audio_tokens, audio_cost_usd, audio_duration_seconds
                    FROM audit_records WHERE filename = ?
                """, (filename,)).fetchone()
                
                # Check if we need to update
                needs_update = True
                if existing is not None:
                    # Handle sqlite returning REAL as float or int interchangeably by comparing rounded values
                    ex_list = list(existing)
                    if len(ex_list) == len(record_values):
                        needs_update = False
                        for i in range(len(ex_list)):
                            val1 = ex_list[i] if ex_list[i] is not None else 0
                            val2 = record_values[i] if record_values[i] is not None else 0
                            if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                                if abs(float(val1) - float(val2)) > 0.0001:
                                    needs_update = True
                                    break
                            elif val1 != val2:
                                needs_update = True
                                break

                if not needs_update:
                    continue
                    
                cur.execute("""
                    INSERT INTO audit_records (
                        filename, symbol, company_name, completed_at, model_name,
                        ocr_size_mb, ocr_tokens, ocr_cost_usd,
                        summary_size_mb, summary_tokens, summary_cost_usd,
                        translation_size_mb, translation_tokens, translation_cost_usd,
                        audio_size_mb, audio_tokens, audio_cost_usd, audio_duration_seconds
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(filename) DO UPDATE SET
                        completed_at=excluded.completed_at,
                        company_name=excluded.company_name,
                        symbol=excluded.symbol,
                        ocr_size_mb=excluded.ocr_size_mb, ocr_tokens=excluded.ocr_tokens, ocr_cost_usd=excluded.ocr_cost_usd,
                        summary_size_mb=excluded.summary_size_mb, summary_tokens=excluded.summary_tokens, summary_cost_usd=excluded.summary_cost_usd,
                        translation_size_mb=excluded.translation_size_mb, translation_tokens=excluded.translation_tokens, translation_cost_usd=excluded.translation_cost_usd,
                        audio_size_mb=excluded.audio_size_mb, audio_tokens=excluded.audio_tokens, audio_cost_usd=excluded.audio_cost_usd,
                        audio_duration_seconds=excluded.audio_duration_seconds,
                        model_name=excluded.model_name,
                        scanned_at=CURRENT_TIMESTAMP
                """, record_values)
                new_records += 1
            except Exception as e:  # noqa: BLE001 - isolate malformed manifests
                logger.error(f"Error processing manifest {manifest_path.name}: {e}")
        
        conn.commit()
        if new_records > 0:
            logger.info(f"Telemetry Scan complete. Updated {new_records} records in audit.db.")
    except Exception as e:  # noqa: BLE001 - keep the background scanner alive
        logger.error(f"Telemetry scan failed: {e}")
    finally:
        conn.close()

async def telemetry_loop():
    logger.info("Telemetry background scanner started.")
    while not telemetry_stop_event.is_set():
        await asyncio.to_thread(_run_scan)
        try:
            await asyncio.wait_for(telemetry_stop_event.wait(), timeout=10)
        except TimeoutError:
            pass

def start_telemetry_scanner():
    global telemetry_task
    init_db()
    telemetry_stop_event.clear()
    if telemetry_task is None or telemetry_task.done():
        telemetry_task = asyncio.create_task(telemetry_loop(), name="briefcast-telemetry")

async def stop_telemetry_scanner():
    telemetry_stop_event.set()
    if telemetry_task:
        await telemetry_task

def fetch_audit_records():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM audit_records ORDER BY completed_at DESC")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def fetch_audit_daily():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM audit_daily_summary ORDER BY audit_date DESC")
        results = [dict(r) for r in cur.fetchall()]
        for row in results:
            row["body"] = "Voice Attached"
        return results
    finally:
        conn.close()

import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from src.settings import PROCESSED_DOCS_DIR

logger = logging.getLogger("uvicorn.info")

PROJECT_ROOT = PROCESSED_DOCS_DIR.parent
DB_DIR = PROJECT_ROOT / "db-init"
DB_PATH = DB_DIR / "audit.db"
INIT_SQL_PATH = DB_DIR / "init.sql"

telemetry_task = None
telemetry_stop_event = asyncio.Event()

def get_db():
    # Ensure db directory exists
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    # Only run init.sql if the database is completely empty (no tables)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(name) FROM sqlite_master WHERE type='table' AND name='audit_records'")
        if cur.fetchone()[0] == 1:
            return  # Database already exists and has tables
            
        if INIT_SQL_PATH.exists():
            with open(INIT_SQL_PATH, 'r', encoding='utf-8') as f:
                sql_script = f.read()
            conn.executescript(sql_script)
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
    finally:
        conn.close()

def _run_scan():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT model_name, input_cost_per_million, output_cost_per_million FROM model_pricing")
        pricing = {row['model_name']: dict(row) for row in cur.fetchall()}
        
        # OPTIMIZATION: Get all filenames currently in the database to avoid reprocessing
        cur.execute("SELECT filename FROM audit_records")
        processed_filenames = {row['filename'] for row in cur.fetchall()}
        
        manifests = list(PROCESSED_DOCS_DIR.glob("*_manifest.json"))
        
        new_records = 0
        for manifest_path in manifests:
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                    
                filename = manifest.get("original_filename")
                if not filename or filename in processed_filenames:
                    continue
                
                cur.execute("SELECT completed_at FROM audit_records WHERE filename = ?", (filename,))
                row = cur.fetchone()
                manifest_completed_at = manifest.get("completed_at")
                
                if row and row['completed_at'] == manifest_completed_at:
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
                audio_cost_usd = get_cost(audio_tokens, "gemini-2.5-flash-preview-tts")
                    
                cur.execute("""
                    INSERT INTO audit_records (
                        filename, symbol, company_name, completed_at, model_name,
                        ocr_size_mb, ocr_tokens, ocr_cost_usd,
                        summary_size_mb, summary_tokens, summary_cost_usd,
                        translation_size_mb, translation_tokens, translation_cost_usd,
                        audio_size_mb, audio_tokens, audio_cost_usd
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(filename) DO UPDATE SET
                        completed_at=excluded.completed_at,
                        company_name=excluded.company_name,
                        symbol=excluded.symbol,
                        ocr_size_mb=excluded.ocr_size_mb, ocr_tokens=excluded.ocr_tokens, ocr_cost_usd=excluded.ocr_cost_usd,
                        summary_size_mb=excluded.summary_size_mb, summary_tokens=excluded.summary_tokens, summary_cost_usd=excluded.summary_cost_usd,
                        translation_size_mb=excluded.translation_size_mb, translation_tokens=excluded.translation_tokens, translation_cost_usd=excluded.translation_cost_usd,
                        audio_size_mb=excluded.audio_size_mb, audio_tokens=excluded.audio_tokens, audio_cost_usd=excluded.audio_cost_usd
                """, (
                    filename, symbol, company_name, manifest_completed_at, model_name,
                    ocr_size_mb, ocr_tokens, ocr_cost_usd,
                    summary_size_mb, summary_tokens, summary_cost_usd,
                    translation_size_mb, translation_tokens, translation_cost_usd,
                    audio_size_mb, audio_tokens, audio_cost_usd
                ))
                new_records += 1
            except Exception as e:
                logger.error(f"Error processing manifest {manifest_path.name}: {e}")
        
        conn.commit()
        if new_records > 0:
            logger.info(f"Telemetry Scan complete. Updated {new_records} records in audit.db.")
    except Exception as e:
        logger.error(f"Telemetry scan failed: {e}")
    finally:
        conn.close()

async def telemetry_loop():
    logger.info("Telemetry background scanner started.")
    while not telemetry_stop_event.is_set():
        await asyncio.to_thread(_run_scan)
        try:
            await asyncio.wait_for(telemetry_stop_event.wait(), timeout=10)
        except asyncio.TimeoutError:
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

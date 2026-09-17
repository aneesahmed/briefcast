import asyncio
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

# Setup directories relative to audit-api folder
PROJECT_ROOT = Path(__file__).parent.parent
PROCESSED_FILES_DIR = PROJECT_ROOT / "processed_files"
FAILED_FILES_DIR = PROJECT_ROOT / "failed_files"
DB_PATH = PROJECT_ROOT / "db-init" / "audit.db"
INIT_SQL_PATH = PROJECT_ROOT / "db-init" / "init.sql"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("audit_api")

app = FastAPI(title="Briefcast Audit Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_db()
    try:
        with open(INIT_SQL_PATH, 'r', encoding='utf-8') as f:
            sql_script = f.read()
        conn.executescript(sql_script)
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
    finally:
        conn.close()

init_db()

def _run_scan():
    logger.info("Starting folder scan for dashboard...")
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT model_name, input_cost_per_million, output_cost_per_million FROM model_pricing")
        pricing = {row['model_name']: dict(row) for row in cur.fetchall()}
        
        manifests = list(PROCESSED_FILES_DIR.glob("*_manifest.json"))
        
        new_records = 0
        for manifest_path in manifests:
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                
                filename = manifest.get("original_filename")
                if not filename:
                    continue
                
                cur.execute("SELECT completed_at FROM audit_records WHERE filename = ?", (filename,))
                row = cur.fetchone()
                manifest_completed_at = manifest.get("completed_at")
                
                if row and row['completed_at'] == manifest_completed_at:
                    continue
                
                company_name = manifest.get("company_name", "")
                symbol = manifest.get("symbol", "")
                
                def get_size_mb(fname):
                    p = PROCESSED_FILES_DIR / fname if fname else None
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
        logger.info(f"Scan complete. Updated {new_records} records.")
    except Exception as e:
        logger.error(f"Scan failed: {e}")
    finally:
        conn.close()

@app.post("/api/audit/scan")
async def trigger_scan(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_scan)
    return {"status": "scanning"}

@app.get("/api/audit/records")
def get_audit_records():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM audit_records ORDER BY completed_at DESC")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

@app.get("/api/audit/daily")
def get_audit_daily():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM audit_daily_summary ORDER BY audit_date DESC")
        results = [dict(r) for r in cur.fetchall()]
        for row in results:
            row["body"] = "voice_attached"
        return results
    finally:
        conn.close()

if __name__ == "__main__":
    _run_scan()
    uvicorn.run("main:app", host="0.0.0.0", port=82, reload=True)

import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
import aiosqlite
from typing import Any

from src.settings import PROCESSED_DOCS_DIR

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_PATH = DB_DIR / "audit_telemetry.db"
MODEL_PRICING_PATH = Path(__file__).resolve().parent.parent.parent / "model_pricing.json"

async def init_audit_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_records (
                filename TEXT PRIMARY KEY,
                job_id TEXT,
                company_name TEXT,
                symbol TEXT,
                completed_at TIMESTAMP,
                
                total_cost_cents REAL DEFAULT 0.0,
                ocr_cost_cents REAL DEFAULT 0.0,
                summary_cost_cents REAL DEFAULT 0.0,
                translation_cost_cents REAL DEFAULT 0.0,
                audio_cost_cents REAL DEFAULT 0.0,
                
                total_tokens INTEGER DEFAULT 0,
                ocr_input_tokens INTEGER DEFAULT 0,
                ocr_output_tokens INTEGER DEFAULT 0,
                summary_input_tokens INTEGER DEFAULT 0,
                summary_output_tokens INTEGER DEFAULT 0,
                translation_input_tokens INTEGER DEFAULT 0,
                translation_output_tokens INTEGER DEFAULT 0,
                audio_input_tokens INTEGER DEFAULT 0,
                audio_output_tokens INTEGER DEFAULT 0,
                
                is_legacy_estimate BOOLEAN DEFAULT 0
            )
        """)
        
        await db.commit()

def load_pricing() -> dict[str, Any]:
    try:
        with open(MODEL_PRICING_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def compute_cost_cents(inp: int, out: int, model: str, pricing: dict) -> float:
    price = pricing.get(model)
    if price:
        cost_usd = (inp / 1_000_000) * price.get("input_cost_per_million", 0) + \
                   (out / 1_000_000) * price.get("output_cost_per_million", 0)
        return round(cost_usd * 100, 4)
    return 0.0

def get_file_size(filename: str | None) -> int:
    if not filename: return 0
    p = Path(PROCESSED_DOCS_DIR) / filename
    return p.stat().st_size if p.exists() else 0

async def process_manifest(manifest_path: Path, db: aiosqlite.Connection, pricing: dict):
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to read manifest {manifest_path.name}: {e}")
        return

    filename = data.get("original_filename") or manifest_path.name.replace("_manifest.json", ".pdf")
    job_id = data.get("job_id", "")
    company_name = data.get("company_name", "")
    symbol = data.get("symbol", "")
    completed_at = data.get("completed_at") or data.get("source_file_date")
    
    # Check if this is a new schema manifest
    if "total_cost_cents" in data:
        # V2 schema: Exact extraction
        is_legacy = False
        
        ocr_m = data.get("ocr_metrics", {})
        sum_m = data.get("summary_metrics", {})
        tra_m = data.get("translation_metrics", {})
        aud_m = data.get("audio_metrics", {})
        
        total_cost = data.get("total_cost_cents", 0.0)
        ocr_cost = ocr_m.get("cost_cents", 0.0)
        sum_cost = sum_m.get("cost_cents", 0.0)
        tra_cost = tra_m.get("cost_cents", 0.0)
        aud_cost = aud_m.get("cost_cents", 0.0)
        
        ocr_in = ocr_m.get("input_tokens", 0)
        ocr_out = ocr_m.get("output_tokens", 0)
        sum_in = sum_m.get("input_tokens", 0)
        sum_out = sum_m.get("output_tokens", 0)
        tra_in = tra_m.get("input_tokens", 0)
        tra_out = tra_m.get("output_tokens", 0)
        aud_in = aud_m.get("input_tokens", 0)
        aud_out = aud_m.get("output_tokens", 0)
        
    else:
        # V1 schema: Estimate everything
        is_legacy = True
        
        # We don't have accurate OCR tokens, assume 0 for legacy files since it wasn't tracked
        ocr_in = ocr_out = 0
        ocr_cost = 0.0
        
        # Estimate summary tokens (read txt file)
        sum_size = get_file_size(data.get("summary_file"))
        sum_in = int(sum_size * 2) # Arbitrary fallback estimate: input was ~2x output
        sum_out = int(sum_size / 4) # English characters / 4
        sum_cost = compute_cost_cents(sum_in, sum_out, "gemini-3.7-flash", pricing)
        
        # Estimate translation tokens
        tra_size = get_file_size(data.get("translation_file"))
        tra_in = sum_out # input was english summary
        tra_out = int(tra_size / 2.5) # Urdu characters / 2.5
        tra_cost = compute_cost_cents(tra_in, tra_out, "gemini-3.7-flash", pricing)
        
        # Estimate audio tokens
        aud_in = int(tra_size / 2) # TTS is billed on character length. Urdu is ~2 bytes per char.
        aud_out = 0
        aud_cost = compute_cost_cents(aud_in, aud_out, "gemini-2.5-flash-preview-tts", pricing)
        
        total_cost = round(ocr_cost + sum_cost + tra_cost + aud_cost, 4)
        
    total_tokens = sum([ocr_in, ocr_out, sum_in, sum_out, tra_in, tra_out, aud_in, aud_out])
    
    await db.execute("""
        INSERT INTO audit_records (
            filename, job_id, company_name, symbol, completed_at,
            total_cost_cents, ocr_cost_cents, summary_cost_cents, translation_cost_cents, audio_cost_cents,
            total_tokens, ocr_input_tokens, ocr_output_tokens, 
            summary_input_tokens, summary_output_tokens,
            translation_input_tokens, translation_output_tokens,
            audio_input_tokens, audio_output_tokens,
            is_legacy_estimate
        ) VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        ) ON CONFLICT(filename) DO UPDATE SET
            job_id=excluded.job_id,
            company_name=excluded.company_name,
            symbol=excluded.symbol,
            completed_at=excluded.completed_at,
            total_cost_cents=excluded.total_cost_cents,
            ocr_cost_cents=excluded.ocr_cost_cents,
            summary_cost_cents=excluded.summary_cost_cents,
            translation_cost_cents=excluded.translation_cost_cents,
            audio_cost_cents=excluded.audio_cost_cents,
            total_tokens=excluded.total_tokens,
            ocr_input_tokens=excluded.ocr_input_tokens,
            ocr_output_tokens=excluded.ocr_output_tokens,
            summary_input_tokens=excluded.summary_input_tokens,
            summary_output_tokens=excluded.summary_output_tokens,
            translation_input_tokens=excluded.translation_input_tokens,
            translation_output_tokens=excluded.translation_output_tokens,
            audio_input_tokens=excluded.audio_input_tokens,
            audio_output_tokens=excluded.audio_output_tokens,
            is_legacy_estimate=excluded.is_legacy_estimate
    """, (
        filename, job_id, company_name, symbol, completed_at,
        total_cost, ocr_cost, sum_cost, tra_cost, aud_cost,
        total_tokens, ocr_in, ocr_out, sum_in, sum_out, tra_in, tra_out, aud_in, aud_out,
        is_legacy
    ))

async def run_audit_scanner_loop():
    logger.info("Starting audit telemetry background scanner (SQLite WAL)...")
    await init_audit_db()
    
    while True:
        try:
            pricing = load_pricing()
            async with aiosqlite.connect(DB_PATH) as db:
                p_dir = Path(PROCESSED_DOCS_DIR)
                if p_dir.exists():
                    manifests = list(p_dir.glob("*_manifest.json"))
                    for manifest_path in manifests:
                        await process_manifest(manifest_path, db, pricing)
                await db.commit()
        except Exception as e:
            logger.error(f"Error in audit scanner loop: {e}")
            
        await asyncio.sleep(60)

_audit_task = None

def start_audit_scanner():
    global _audit_task
    if _audit_task is None:
        _audit_task = asyncio.create_task(run_audit_scanner_loop())
        
def stop_audit_scanner():
    global _audit_task
    if _audit_task:
        _audit_task.cancel()
        _audit_task = None

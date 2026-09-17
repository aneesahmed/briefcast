# Session Memory: Briefcast Financials & Audit Dashboard (Sep 13)

## Status
- **Current State:** The backend pipeline was previously updated to record accurate API costs (`cost_cents`) and tokens directly into the `_manifest.json` files.
- **Server Data Import:** The user copied over `processed_files` and `failed_files` from the production server.
- **Data Reality:** 
  - ~34 files were processed with the new v2 schema (contains `total_cost_cents`, `ocr_metrics`, etc.).
  - ~152 older files were processed with the v1 schema (no cost/token metrics).
- **Next Step (Morning):** Implement Phase 1 of the Financials Dashboard as outlined in the `FINANCIALS_SYSTEM_PLAN.md` artifact.

## Action Plan to Resume (Phase 1)
1. **Review Database Schema:** Update `db-init/init.sql` (`audit_records` table) to support both the exact costs from v2 files and estimated costs from v1 files.
2. **Build the Ingestion Loop (`audit_scanner.py`):** 
   - Create a FastAPI background task that loops through `processed_files/`.
   - Read each `_manifest.json`.
   - If it has `total_cost_cents` -> insert exact metrics.
   - If it doesn't -> estimate tokens based on file sizes (chars/4 for EN, chars/1.25 for UR) and compute costs using `model_pricing.json`, then insert.
   - Upsert these records into PostgreSQL.

## Notes
- We reverted the `_summary_audio.mp3` naming scheme back to the clean `_audio.mp3` / `_translation.txt` format.
- The date filtering endpoint `/api/audio/by-date` was successfully updated to filter based on `completed_at` (JSON generation time) rather than `source_file_date`.
- We added `backend/.env`, `backend/runtime.bat`, and a global `__pycache__/` rule to `.gitignore`.

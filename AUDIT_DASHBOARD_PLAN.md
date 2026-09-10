# Briefcast Audit & Financial Dashboard — Implementation Spec

Status: **planning complete, not yet implemented**. This document is a self-contained handoff
so a separate agent/session can build this without re-deriving context from chat history.

## Goal

Add an "Audit & Financials" view to the existing Briefcast dashboard showing, per processed
document and in aggregate (including per-day): file size on disk, estimated LLM tokens consumed,
and estimated cost. None of this data exists today — `processed_files/*_manifest.json` contains
no token/cost telemetry (verified by inspecting `processed_files/282049_manifest.json`), so it
must be computed from what's on disk.

## Constraints / decisions already made (do not re-litigate)

- **Backend (Python/FastAPI) may be modified**, but only additively — a new scanner module and
  new read endpoints. Do **not** modify existing pipeline logic, existing routes, `models.py`,
  or `agent_graph.py`.
- **Database: PostgreSQL**, run as a new service in the existing `docker-compose.yml`, not
  SQLite. Rationale: near-zero setup cost via the existing compose file, proper concurrent
  read/write, and native `GROUP BY` for daily cost aggregation. (If Postgres turns out to be
  unavailable in the target environment, SQLite via `sqlite3`/`better-sqlite3` is the documented
  fallback — same schema, minus per-day materialized aggregation.)
- **One writer, Postgres is the shared source of truth**: the FastAPI background scanner is the
  *only* process that writes to `audit_records`. The Node/Express service and the React frontend
  only ever read.
- **Audit dashboard runs as its own service, own port, no dependency on FastAPI being up** —
  it depends only on the Postgres database being reachable, not on the FastAPI process.
- **Frontend stays React + TypeScript** (Vite), folded into the existing dashboard app at
  `frontend/` — not a separate mini-app. Delete the disconnected prototype
  (`frontend/audit.html`, `frontend/vite.audit.config.ts`, `frontend/src/audit-main.tsx`) as
  part of this work.
- **Token counts and costs are estimates**, not real usage data (Gemini responses aren't
  currently captured with usage metadata anywhere in the pipeline). Every UI surface showing
  these numbers must visibly label them as estimated.
- **Pricing is not guessable** — real per-token/per-character rates for `gemini-3.7-flash`,
  `gemini-2.5-flash-preview-tts`, `gemini-3.1-flash-tts-preview` must be supplied by a human and
  are stored in a DB table (`model_pricing`) so they can be corrected without a code deploy.

## Architecture

```
                     every 10s, reads processed_files/*
                     (manifest + summary + translation + audio)
┌─────────────────┐  only new/changed files (mtime check)   ┌──────────────┐
│  FastAPI backend │ ───────────────────────────────────────▶│  PostgreSQL  │
│  (existing app,  │   upserts into audit_records             │  audit_records│
│  + new scanner   │                                          │  model_pricing│
│  module)         │                                          └──────┬───────┘
└─────────────────┘                                                  │ read-only
                                                                       ▼
                                                          ┌────────────────────┐
                                                          │  Express service    │
                                                          │  (own port, TS)     │
                                                          │  /api/audit/*       │
                                                          │  + serves built     │
                                                          │  React dist/        │
                                                          └─────────┬──────────┘
                                                                    │ fetch
                                                                    ▼
                                                          ┌────────────────────┐
                                                          │  React dashboard    │
                                                          │  "Audit &           │
                                                          │  Financials" tab    │
                                                          └────────────────────┘
```

FastAPI's existing HTTP API is never in this dashboard's request path. The only coupling
between the two services is the Postgres database.

## 1. Database schema

```sql
-- One row per source document (identified by its original filename).
-- Re-processing the same file UPDATEs the row rather than inserting a duplicate.
CREATE TABLE audit_records (
    filename                TEXT PRIMARY KEY,       -- e.g. "282049.pdf", matches manifest.original_filename
    job_id                  TEXT,                    -- most recent job_id from the manifest
    title                   TEXT,
    company_name            TEXT,
    symbol                  TEXT,
    source_file_date        DATE,                    -- manifest.source_file_date
    completed_at            TIMESTAMPTZ,              -- manifest.completed_at; primary change-detection signal
    manifest_mtime          TIMESTAMPTZ,              -- filesystem mtime of the *_manifest.json, fallback signal

    source_size_bytes       BIGINT NOT NULL DEFAULT 0,
    audio_size_bytes        BIGINT NOT NULL DEFAULT 0,
    summary_size_bytes      BIGINT NOT NULL DEFAULT 0,
    translation_size_bytes  BIGINT NOT NULL DEFAULT 0,
    total_size_bytes        BIGINT GENERATED ALWAYS AS (
        source_size_bytes + audio_size_bytes + summary_size_bytes + translation_size_bytes
    ) STORED,

    summary_model            TEXT,                   -- from backend/src/settings.py at scan time
    translation_model        TEXT,
    audio_model               TEXT,

    estimated_input_tokens    INTEGER NOT NULL DEFAULT 0,
    estimated_output_tokens   INTEGER NOT NULL DEFAULT 0,
    estimated_total_tokens    INTEGER GENERATED ALWAYS AS (
        estimated_input_tokens + estimated_output_tokens
    ) STORED,
    estimated_tts_characters  INTEGER NOT NULL DEFAULT 0,

    estimated_cost_usd        NUMERIC(12, 6) NOT NULL DEFAULT 0,

    status                     TEXT NOT NULL DEFAULT 'completed',  -- 'completed' | 'error'
    last_scanned_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_records_source_file_date ON audit_records (source_file_date);
CREATE INDEX idx_audit_records_completed_at ON audit_records (completed_at);

-- Editable pricing, kept out of code so it can be corrected without a deploy.
-- unit_type distinguishes token-priced text models from character-priced TTS models.
CREATE TABLE model_pricing (
    model_name          TEXT PRIMARY KEY,             -- must match SUMMARY_MODEL / TRANSLATION_MODEL / AUDIO_MODEL
    unit_type            TEXT NOT NULL CHECK (unit_type IN ('token', 'character')),
    input_price_per_unit  NUMERIC(14, 8) NOT NULL DEFAULT 0,  -- USD per token or per character
    output_price_per_unit NUMERIC(14, 8) NOT NULL DEFAULT 0,
    currency               TEXT NOT NULL DEFAULT 'USD',
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed rows — PLACEHOLDER VALUES, must be replaced with real rates before this is trustworthy.
INSERT INTO model_pricing (model_name, unit_type, input_price_per_unit, output_price_per_unit) VALUES
    ('gemini-3.7-flash', 'token', 0, 0),
    ('gemini-2.5-flash-preview-tts', 'character', 0, 0),
    ('gemini-3.1-flash-tts-preview', 'character', 0, 0)
ON CONFLICT (model_name) DO NOTHING;

-- Reporting view for per-day totals — used by GET /api/audit/daily.
CREATE VIEW audit_daily_summary AS
SELECT
    source_file_date,
    COUNT(*)                       AS file_count,
    SUM(total_size_bytes)          AS total_size_bytes,
    SUM(estimated_total_tokens)    AS total_tokens,
    SUM(estimated_tts_characters)  AS total_tts_characters,
    SUM(estimated_cost_usd)        AS total_cost_usd
FROM audit_records
GROUP BY source_file_date
ORDER BY source_file_date DESC;
```

Change-detection rule for the scanner: skip a file if `completed_at` (or, if absent,
`manifest_mtime`) equals what's already stored for that `filename`. Only recompute and
`UPSERT` when it differs or the row doesn't exist yet.

## 2. Backend addition (FastAPI)

New file: `backend/src/services/audit_scanner.py`

- Background loop, same shape as `scanner_loop()` in `backend/src/api/routes.py`, interval
  10 seconds (own constant, not tied to `SCANNER_INTERVAL_SECONDS`).
- Each tick:
  1. `os.scandir(PROCESSED_FILES_DIR)` for `*_manifest.json`.
  2. For each manifest, read `mtime` cheaply via `stat()`; compare against the stored
     `manifest_mtime` for that `filename` (one indexed lookup). Skip if unchanged.
  3. For new/changed manifests only: parse the JSON, stat the companion source/audio/summary/
     translation files for sizes, estimate tokens (see below), look up current model names from
     `backend/src/settings.py`, look up pricing from `model_pricing`, compute
     `estimated_cost_usd`.
  4. `UPSERT` into `audit_records`.
- Token estimation function (pure, unit-testable): character-count heuristic, language-aware
  (Urdu text ≈ higher chars-per-token ratio than English — mirror the logic already prototyped
  in the deleted `vite.audit.config.ts`: roughly `len * 0.25` for English/Latin text, `len * 0.8`
  characters-to-token-ish for Urdu — tune during implementation, and clearly comment that this
  is an approximation, not a real tokenizer).
- Started in `backend/src/main.py`'s startup event alongside the existing scanner; stopped on
  shutdown the same way.
- New dependency: an async Postgres driver (`asyncpg` recommended, consistent with the rest of
  the app being `async`).
- New read-only endpoints for convenience/debugging only (the dashboard itself talks to Postgres
  via the Express service, not these) — optional, low priority:
  - `GET /api/audit/health` — confirms the scanner is running and Postgres is reachable.

## 3. Audit service (Node + TypeScript + Express)

New workspace, e.g. `audit-service/` at the project root (sibling to `backend/` and `frontend/`).

- `src/db.ts` — `pg` (node-postgres) pool, read-only role/user against the same Postgres
  instance.
- `src/routes/audit.ts`:
  - `GET /api/audit/records?from=&to=&company=&symbol=` — rows from `audit_records`, filterable.
  - `GET /api/audit/summary` — `SELECT COUNT(*), SUM(total_size_bytes), SUM(estimated_total_tokens), SUM(estimated_cost_usd) FROM audit_records`.
  - `GET /api/audit/daily?days=30` — reads from `audit_daily_summary`.
- `src/index.ts` — Express app; in production, `express.static()` serves `frontend/dist/`; runs
  on its own configurable port (e.g. `AUDIT_SERVICE_PORT`, default `4100`).
- Env: `DATABASE_URL` pointing at the Postgres instance (read-only credentials).

## 4. Frontend (React + TypeScript, folded into `frontend/`)

- Delete: `frontend/audit.html`, `frontend/vite.audit.config.ts`, `frontend/src/audit-main.tsx`.
- New `frontend/src/types/audit.ts` — types matching the Express API responses above (distinct
  from the existing, currently-unused `TelemetryMetrics`/`CostMetrics` in `frontend/src/types.ts`,
  which describe data that has never existed — those should be removed once this replaces them).
- New `frontend/src/services/auditApi.ts` — `fetch` wrapper against
  `import.meta.env.VITE_AUDIT_API_URL` (defaults to `http://localhost:4100`).
- New tab/section in `frontend/src/App.tsx`: "Audit & Financials", built from
  `frontend/src/components/Audit.tsx`'s existing layout conventions, rewired to the real fields:
  per-file table (filename, company, size, estimated tokens, estimated cost, date), a totals
  strip, and a per-day cost table/chart from `/api/audit/daily`.
- Every number sourced from `estimated_*` columns must carry an "estimated" label/tooltip in the
  UI — this is not metered usage data.

## 5. Docker Compose addition

Add to `docker-compose.yml`:

```yaml
  audit-db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: briefcast_audit
      POSTGRES_USER: briefcast
      POSTGRES_PASSWORD: <set via .env, not committed>
    volumes:
      - audit-db-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped

volumes:
  audit-db-data:
```

The `briefcast` (FastAPI) service and a new `audit-service` container both get a `DATABASE_URL`
pointing at `audit-db`, via env files — FastAPI with write credentials, `audit-service` with
read-only credentials.

## 6. Open items that need a human decision before/while implementing

1. **Real pricing** for `gemini-3.7-flash`, `gemini-2.5-flash-preview-tts`,
   `gemini-3.1-flash-tts-preview` — `model_pricing` ships with zeros until supplied.
2. **Postgres credentials/secrets** — where they live (`.env`, not committed) and who has write
   vs. read-only access.
3. **Token-estimation heuristic tuning** — the char-count multipliers are a starting point, not
   verified against real Gemini tokenization.
4. Confirm `completed_at` in the manifest is only ever written once per successful run (so it's
   a reliable change-detection signal) — verify against `finalize_source_file()` in
   `backend/src/api/routes.py` before relying on it.

## 7. Explicit non-goals

- No changes to the existing document processing pipeline, routes, or models.
- No real-time token/cost capture from actual Gemini API responses (would require a backend
  pipeline change beyond scope here — noted as a possible future improvement, not part of this
  work).
- No auth added to the new endpoints (matches the rest of the app's current unauthenticated
  state — flagged separately as a pre-existing production-readiness gap, not something this
  feature should quietly fix or quietly worsen).

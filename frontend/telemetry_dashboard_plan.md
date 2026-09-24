# Briefcast Frontend Roadmap: Telemetry Dashboard

## Current Status (Backend Completed)
The backend telemetry infrastructure is fully completed, optimized, and integrated directly into the main FastAPI application on Port 8000.
*   **Database:** A SQLite database (`audit.db`) is automatically initialized from `init.sql` (only if it doesn't already exist).
*   **Background Scanner:** A background task runs every 10 seconds to scan for new `_manifest.json` files.
*   **Optimizations:** It queries `MAX(completed_at)` from the database and only opens/reads manifests that are newer than the last recorded entry, preventing unnecessary CPU load.
*   **Endpoints Ready:**
    *   `GET /api/audit/records`: Returns a JSON array of all processed documents with their individual costs, token usage, and durations.
    *   `GET /api/audit/daily`: Returns a JSON array of daily grouped summaries (e.g., total files, total costs per day).

## Current Phase: Lightweight FastAPI Dashboard (Implemented)

We pivoted from the heavy Next.js frontend to a **Lightweight FastAPI Dashboard**.
The dashboard is now seamlessly hosted by the Python backend on Port 8000.
*   **Location:** `backend/dashboard/`
*   **Access:** `http://localhost:8000/dashboard`
*   **Tech Stack:** Vanilla JavaScript, Chart.js, Tailwind CSS (via CDN).

### Completed Features:
1. **KPI Summary Cards:** Total Spend, Files Processed, Average Cost.
2. **Cost Breakdown Chart:** Pie chart separating OCR, Summary, Translation, and Audio.
3. **Daily Spend Timeline:** Bar chart showing daily budget usage.
4. **Recent Activity Table:** Scrolling list of processed documents and their individual costs.
5. **Advanced Filtering (Added):**
    *   **Date Filter:** Dropdown to select 'All Time', 'Last 7 Days', or 'Last 30 Days'.
    *   **Step Filter:** Dropdown to isolate metrics by pipeline step (e.g., viewing *only* the OCR costs).

## Next Steps for the Morning
*   Review the new dashboard UI and filters at `http://localhost:8000/dashboard`.
*   Decide if any specific chart tweaks or additional filters (e.g., filtering by Symbol/Company) are needed.

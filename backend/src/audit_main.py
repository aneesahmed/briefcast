import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.services.telemetry import fetch_audit_records, fetch_audit_daily

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="Briefcast Telemetry API",
    version="1.0.0",
    description="Dedicated API for the Briefcast Financials & Audit Dashboard.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/audit/records", tags=["Telemetry Dashboard"])
def get_audit_records():
    """Returns the full list of processed documents with individual token and cost metrics."""
    return fetch_audit_records()

@app.get("/api/audit/daily", tags=["Telemetry Dashboard"])
def get_audit_daily():
    """Returns daily aggregations of file counts, token usage, and total costs."""
    return fetch_audit_daily()

# src/main.py

import argparse
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from src.api.routes import (
    router as api_router,
)
from src.api.routes import (
    scanner_runtime_enabled,
    shutdown_folder_scanner,
    start_folder_scanner,
    start_audit_scanner,
    stop_audit_scanner,
)
from src.settings import LOG_FILE_PATH

# Configure logging to write to both console and file
file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

logger = logging.getLogger("uvicorn.error")
logger.addHandler(file_handler)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if scanner_runtime_enabled:
        try:
            await start_folder_scanner()
        except RuntimeError as exc:
            logger.warning("Automatic scanner is paused: %s", exc)
    # await start_audit_scanner() # Disabled DB logic for now
    yield
    # await stop_audit_scanner() # Disabled DB logic for now
    await shutdown_folder_scanner()


app = FastAPI(
    title="Briefcast API",
    version="1.0.0",
    description="Scans source documents and publishes dated Urdu audio broadcasts.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


def custom_openapi():
    """Emit Swagger-compatible binary file fields for multipart uploads."""
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    upload_body = schema["components"]["schemas"].get(
        "Body_upload_documents_api_upload_docs_post"
    )
    if upload_body:
        file_items = upload_body["properties"]["files"]["items"]
        file_items.pop("contentMediaType", None)
        file_items["format"] = "binary"

    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi

def run() -> None:
    """Start Briefcast with command-line arguments."""
    parser = argparse.ArgumentParser(description="Run Briefcast API server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Bind socket to this host.")
    parser.add_argument("--port", type=int, default=8000, help="Bind socket to this port.")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload.")
    
    args = parser.parse_args()
    
    uvicorn.run(
        "src.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    run()

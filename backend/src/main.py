# src/main.py

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv

# Updated: Use 'src.api.routes' (or relative '.api.routes')
from src.api.routes import (
    router as api_router,
    scanner_runtime_enabled,
    shutdown_folder_scanner,
    start_folder_scanner,
)
from src.core.config import (
    APP_MODE,
    FRONTEND_DIST_DIR,
    SERVER_HOST,
    SERVER_PORT,
    SERVER_RELOAD,
    LOG_FILE_PATH,
)

load_dotenv()

# Configure logging to write to both console and file
file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

logger = logging.getLogger("uvicorn.error")
logger.addHandler(file_handler)

if APP_MODE == "live":
    print("WARNING: Starting in LIVE mode. Real API calls will be made, incurring costs.")
    try:
        input("Press Enter to continue or Ctrl+C to cancel...")
    except KeyboardInterrupt:
        print("\nStartup cancelled.")
        exit(1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if scanner_runtime_enabled:
        try:
            await start_folder_scanner()
        except RuntimeError as exc:
            logger.warning("Automatic scanner is paused: %s", exc)
    yield
    await shutdown_folder_scanner()


app = FastAPI(
    title="Briefcast API",
    version="1.0.0",
    description="Processes documents and raw text, executes async LangGraph workflows, and generates Urdu TTS audio broadcasts.",
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


if FRONTEND_DIST_DIR.exists():
    # Register after all API/docs routes so the SPA only handles frontend paths.
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
else:
    @app.get("/", include_in_schema=False)
    async def frontend_not_built():
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Frontend build not found. Run `npm run build` in the frontend directory."
            },
        )

def run() -> None:
    """Start Briefcast using the committed defaults from core/config.py."""
    uvicorn.run(
        "src.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=SERVER_RELOAD,
    )


if __name__ == "__main__":
    run()

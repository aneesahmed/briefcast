# src/main.py

import os
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv

# Updated: Use 'src.api.routes' (or relative '.api.routes')
from src.api.routes import router as api_router

load_dotenv()

app = FastAPI(
    title="Briefcast API",
    version="1.0.0",
    description="Processes documents and raw text, executes async LangGraph workflows, and generates Urdu TTS audio broadcasts.",
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

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)

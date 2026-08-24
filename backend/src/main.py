# src/main.py

import os
from fastapi import FastAPI
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
# Briefcast

Briefcast automatically processes documents into an English summary, Urdu translation, and MP3 broadcast using Gemini. FastAPI serves both the API and the compiled React dashboard from one port.

## Project Structure
- `backend/`: FastAPI application managing the orchestration pipeline, AI models, and document processing.
- `frontend/`: React application built with Vite and TypeScript for interacting with the Briefcast system.

## Getting Started

### Using Docker (Recommended)
You can spin up the entire application using Docker Compose.

1. Ensure Docker and Docker Compose are installed.
2. Provide your environment variables:
   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env to add your GEMINI_API_KEY and other details
   ```
3. Start the containers:
   ```bash
   docker-compose up --build
   ```
4. Open the dashboard at `http://localhost:8000` or Swagger at `http://localhost:8000/docs`.

### Local setup

Build the dashboard once, then run the complete application with Uvicorn:

```powershell
cd frontend
npm install
npm run build

cd ../backend
Copy-Item .env.example .env
# Add GEMINI_API_KEY to backend/.env
uv sync
uv run python -m src.main
```

Only rebuild the frontend after changing React code; no separate React server is required.

# Briefcast Backend

This is the FastAPI backend for the Briefcast system. It uses LangGraph to orchestrate stateful document summarization, translation to Urdu, and TTS generation.

## Requirements
- Python 3.12
- Node.js (only to compile the dashboard)
- [uv](https://github.com/astral-sh/uv) (for dependency management)

## Setup
1. Copy the environment variables template and configure it:
   ```bash
   cp .env.example .env
   ```
   Add your `GEMINI_API_KEY`.

2. Install dependencies using `uv`:
   ```bash
   uv sync
   ```

3. Build the dashboard from the project root:
   ```bash
   cd ../frontend
   npm install
   npm run build
   cd ../backend
   ```

4. Run the complete application:
   ```bash
   uv run python -m src.main
   ```

The dashboard is available at `http://localhost:8000`; the API documentation is at `/docs`.

## Running Tests
Run the test suite with:
```bash
uv run pytest
```

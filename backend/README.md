# Briefcast Backend

This is the FastAPI backend for the Briefcast system. It uses LangGraph to orchestrate stateful document summarization, translation to Urdu, and TTS generation.

## Requirements
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (for dependency management)

## Setup
1. Copy the environment variables template and configure it:
   ```bash
   cp .env.example .env
   ```
   Add your `GEMINI_API_KEY` and other necessary credentials.

2. Install dependencies using `uv`:
   ```bash
   uv venv
   # Windows: .venv\Scripts\activate
   # Linux/Mac: source .venv/bin/activate
   uv pip install -r pyproject.toml
   ```

3. Run the development server:
   ```bash
   uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
   ```

## Running Tests
Run the test suite with:
```bash
bash run_tests.sh
```

# Briefcast Backend

Briefcast is a folder-driven FastAPI service. It scans `briefing_source` every five seconds and processes supported TXT, PDF, and DOCX files sequentially.

For each source document, the service:

1. Generates an English summary with Gemini.
2. Translates the summary into Urdu with Gemini.
3. Generates an Urdu MP3 with Gemini TTS.
4. Moves the source and generated artifacts to `processed_files`.
5. Moves the source and an error record to `failed_files` if processing fails.

## Setup

The backend requires Python 3.12 and `uv`.

```powershell
cd C:\working\AI26\briefcast\backend
Copy-Item .env.example .env
uv sync
```

Set only the Gemini secret in `.env`:

```dotenv
GEMINI_API_KEY=your_gemini_api_key
```

Model names, the 120-word summary limit, scanner interval, server host, and server port are committed in `src/core/config.py`.

## Run

```powershell
uv run python -m src.main
```

Swagger documentation is available at `http://localhost:8000/docs`.

## Consumer API

Get audio completed on a date:

```http
GET /api/audio/by-date?date=2026-09-03
```

Example response:

```json
{
  "date": "2026-09-03",
  "count": 1,
  "items": [
    {
      "title": "Example Limited",
      "audio_url": "http://localhost:8000/api/audio/example_audio.mp3"
    }
  ]
}
```

The consumer can open `audio_url` to stream or download the MP3.

Other operational endpoints:

- `GET /api/health`
- `POST /api/upload-docs`
- `GET /api/scanner/status`
- `POST /api/scanner/start`
- `POST /api/scanner/stop`
- `POST /api/scanner/scan`

## Tests

```powershell
uv run python -m pytest -q
```

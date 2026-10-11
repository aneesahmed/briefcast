import asyncio
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.api import routes
from src.main import app
from src.models import PipelineConfig
from src.services import agent_graph

client = TestClient(app)


def configure_test_directories(tmp_path, monkeypatch):
    source_dir = tmp_path / "briefing_source"
    processing_dir = tmp_path / "processing_files"
    processed_dir = tmp_path / "processed_files"
    failed_dir = tmp_path / "failed_files"
    source_dir.mkdir()
    processing_dir.mkdir()
    processed_dir.mkdir()
    failed_dir.mkdir()
    monkeypatch.setattr(routes, "INPUT_DOCS_DIR", source_dir)
    monkeypatch.setattr(routes, "PROCESSING_DOCS_DIR", processing_dir)
    monkeypatch.setattr(routes, "PROCESSED_DOCS_DIR", processed_dir)
    monkeypatch.setattr(routes, "FAILED_FILES_DIR", failed_dir)
    monkeypatch.setattr(routes, "scanner_runtime_enabled", True)
    monkeypatch.setattr(routes, "scanner_system_error", None)
    routes.scanner_stop_event.clear()
    routes.active_jobs.clear()
    return source_dir, processed_dir, failed_dir


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Briefcast API"}


def test_gemini_client_is_reused(monkeypatch):
    fake_client = object()
    created = []

    def fake_factory(**kwargs):
        created.append(kwargs)
        return fake_client

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    agent_graph.get_gemini_client.cache_clear()
    monkeypatch.setattr(agent_graph.genai, "Client", fake_factory)

    assert agent_graph.get_gemini_client() is fake_client
    assert agent_graph.get_gemini_client() is fake_client
    assert len(created) == 1
    agent_graph.get_gemini_client.cache_clear()


def test_upload_documents(tmp_path, monkeypatch):
    source_dir, _, _ = configure_test_directories(tmp_path, monkeypatch)
    response = client.post(
        "/api/upload-docs",
        files={"files": ("test_doc.txt", b"Briefcast test document", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["filenames"] == ["test_doc.txt"]
    assert (source_dir / "test_doc.txt").read_text() == "Briefcast test document"


def test_upload_openapi_uses_binary_file_picker():
    schema = client.get("/openapi.json").json()
    upload_schema = schema["components"]["schemas"][
        "Body_upload_documents_api_upload_docs_post"
    ]
    file_items = upload_schema["properties"]["files"]["items"]

    assert file_items["type"] == "string"
    assert file_items["format"] == "binary"
    assert "contentMediaType" not in file_items


def test_scanner_processes_file_directly(tmp_path, monkeypatch):
    source_dir, _, _ = configure_test_directories(tmp_path, monkeypatch)
    source_file = source_dir / "report.txt"
    source_file.write_text("Financial report contents.")
    processed = []

    async def fake_pipeline(transaction_id, filename, content, config, **kwargs):
        processed.append((filename, content, config.summary_max_words))
        routes.active_jobs.pop(transaction_id, None)
        return {"status": "completed"}

    monkeypatch.setattr(routes, "run_pipeline_core", fake_pipeline)
    asyncio.run(routes.scan_input_folder())

    assert processed == [("report.txt", "Financial report contents.", 120)]
    assert routes.active_jobs == {}


def test_existing_artifacts_do_not_block_source_processing(tmp_path, monkeypatch):
    source_dir, processed_dir, _ = configure_test_directories(tmp_path, monkeypatch)
    (processed_dir / "report_audio.mp3").write_bytes(b"old")
    (source_dir / "report.txt").write_text("New report")
    processed_names = []

    async def fake_pipeline(transaction_id, filename, content, config, **kwargs):
        processed_names.append(filename)
        routes.active_jobs.pop(transaction_id, None)
        return {"status": "completed"}

    monkeypatch.setattr(routes, "run_pipeline_core", fake_pipeline)
    asyncio.run(routes.scan_input_folder())

    assert processed_names == ["report.txt"]
    assert (processed_dir / "report_audio.mp3").read_bytes() == b"old"


def test_successful_pipeline_creates_flat_artifacts(tmp_path, monkeypatch):
    _, processed_dir, _ = configure_test_directories(tmp_path, monkeypatch)
    source_file = routes.PROCESSING_DOCS_DIR / "market_report.txt"
    source_file.write_text("Market report contents.", encoding="utf-8")

    async def fake_invoke(state):
        (state["output_dir"] / state["audio_path"]).write_bytes(b"ID3-test")
        return {
            **state,
            "english_summary": "A short English market summary.",
            "urdu_summary": "ایک مختصر اردو خلاصہ۔",
            "summary_metrics": {
                "extracted_data": {"company_name": "Example Limited", "symbol": "EXM"},
                "extracted_name": "Example Limited",
            },
        }

    monkeypatch.setattr(routes, "document_graph", SimpleNamespace(ainvoke=fake_invoke))
    result = asyncio.run(
        routes.run_pipeline_core(
            "workflow-test",
            source_file.name,
            source_file.read_text(encoding="utf-8"),
            PipelineConfig(),
        )
    )

    assert result["status"] == "completed"
    assert result["title"] == "Example Limited"
    assert not source_file.exists()
    assert (processed_dir / "market_report.txt").exists()
    assert (processed_dir / "market_report_summary.txt").read_text(encoding="utf-8") == "A short English market summary."
    assert (processed_dir / "market_report_translation.txt").read_text(encoding="utf-8") == "ایک مختصر اردو خلاصہ۔"
    assert (processed_dir / "market_report_audio.mp3").read_bytes() == b"ID3-test"
    assert (processed_dir / "market_report_manifest.json").exists()


def test_audio_feed_filters_by_date(tmp_path, monkeypatch):
    _, processed_dir, _ = configure_test_directories(tmp_path, monkeypatch)
    monkeypatch.setattr(routes, "encrypt_url", lambda url: url)
    (processed_dir / "example_audio.mp3").write_bytes(b"ID3")
    (processed_dir / "example_manifest.json").write_text(
        json.dumps(
            {
                "title": "Example Limited",
                "original_filename": "example.pdf",
                "audio_file": "example_audio.mp3",
                "completed_at": "2026-09-03T10:30:00",
            }
        ),
        encoding="utf-8",
    )

    response = client.get("/api/audio/by-date", params={"date": "2026-09-03"})
    assert response.status_code == 200
    assert response.json() == {
        "date": "2026-09-03",
        "count": 1,
        "items": [
            {
                "title": "Example Limited",
                "file_name": "example.pdf",
                "symbol": None,
                "company_name": None,
                "audio_url": "http://testserver/api/audio/example_audio.mp3",
                "audio_duration_seconds": 0.0,
                "body": "Voice Attached",
            }
        ],
    }


def test_audio_feed_rejects_invalid_date():
    response = client.get("/api/audio/by-date", params={"date": "03-09-2026"})
    assert response.status_code == 400


def test_audio_download_blocks_path_traversal(tmp_path, monkeypatch):
    configure_test_directories(tmp_path, monkeypatch)
    response = client.get("/api/audio/..%5Cbackend%5Csecret_audio.mp3")
    assert response.status_code == 400


def test_scanner_status_reports_processing_count(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    routes.active_jobs["one"] = {"filename": "report.pdf"}
    status = routes.scanner_status()
    routes.active_jobs.clear()

    assert status["processing_count"] == 1
    assert status["configuration_ready"] is True


def test_system_error_returns_file_and_stops_scanner(tmp_path, monkeypatch):
    source_dir, _, failed_dir = configure_test_directories(tmp_path, monkeypatch)
    source_file = source_dir / "network_test.txt"
    source_file.write_text("Financial report contents.", encoding="utf-8")
    untouched_file = source_dir / "untouched.txt"
    untouched_file.write_text("This file must not be scanned yet.", encoding="utf-8")

    async def fail_pipeline(*args, **kwargs):
        raise ConnectionError("Gemini network is unavailable")

    monkeypatch.setattr(routes, "run_pipeline_core", fail_pipeline)
    asyncio.run(routes.scan_input_folder())

    assert source_file.exists()
    assert untouched_file.exists()
    assert not (failed_dir / source_file.name).exists()
    assert routes.scanner_runtime_enabled is False
    assert routes.scanner_system_error["filename"] == source_file.name
    assert "network is unavailable" in routes.scanner_system_error["error"]


def test_empty_document_moves_to_failed_folder(tmp_path, monkeypatch):
    source_dir, _, failed_dir = configure_test_directories(tmp_path, monkeypatch)
    source_file = source_dir / "empty.txt"
    source_file.write_text("", encoding="utf-8")

    asyncio.run(routes.scan_input_folder())

    assert not source_file.exists()
    assert (failed_dir / source_file.name).exists()
    assert (failed_dir / "empty_error.json").exists()
    assert routes.scanner_runtime_enabled is True
    assert routes.scanner_system_error is None

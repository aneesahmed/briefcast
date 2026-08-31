# tests/test_endpoints.py

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient
from src.api import routes
from src.services import agent_graph
from src.models import PipelineConfig
from tinydb import TinyDB

# Updated: Import from src.main since we renamed the file
from src.main import app

client = TestClient(app)


def test_health_check():
    """Verifies the API is awake and responding."""
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Briefcast API"}


def test_gemini_client_is_reused(monkeypatch):
    fake_client = object()
    created = []

    def fake_factory(**kwargs):
        created.append(kwargs)
        return fake_client

    agent_graph.get_gemini_client.cache_clear()
    monkeypatch.setattr(agent_graph.genai, "Client", fake_factory)

    assert agent_graph.get_gemini_client() is fake_client
    assert agent_graph.get_gemini_client() is fake_client
    assert len(created) == 1
    agent_graph.get_gemini_client.cache_clear()


def test_upload_documents(tmp_path, monkeypatch):
    """Simulates a multipart form-data file upload."""

    source_dir = tmp_path / "briefing_source"
    processed_dir = tmp_path / "processed_files"
    source_dir.mkdir()
    processed_dir.mkdir()
    monkeypatch.setattr(routes, "INPUT_DOCS_DIR", source_dir)
    monkeypatch.setattr(routes, "PROCESSED_DOCS_DIR", processed_dir)

    dummy_file = tmp_path / "test_doc.txt"
    dummy_file.write_text("This is a test document for the Briefcast pipeline.")

    with open(dummy_file, "rb") as f:
        files = {"files": ("test_doc.txt", f, "text/plain")}
        response = client.post("/api/upload-docs", files=files)

    assert response.status_code == 200

    data = response.json()
    assert "Successfully uploaded" in data["message"]
    assert "test_doc.txt" in data["filenames"]
    assert (source_dir / "test_doc.txt").exists()


def test_upload_openapi_uses_binary_file_picker():
    schema = client.get("/openapi.json").json()
    upload_schema = schema["components"]["schemas"][
        "Body_upload_documents_api_upload_docs_post"
    ]
    file_items = upload_schema["properties"]["files"]["items"]

    assert file_items["type"] == "string"
    assert file_items["format"] == "binary"
    assert "contentMediaType" not in file_items


def test_scanner_processes_discovered_file_directly(tmp_path, monkeypatch):
    source_dir = tmp_path / "briefing_source"
    processed_dir = tmp_path / "processed_files"
    failed_dir = tmp_path / "failed_files"
    source_dir.mkdir()
    processed_dir.mkdir()
    failed_dir.mkdir()
    (source_dir / "report.txt").write_text("Financial report contents.")

    test_db = TinyDB(tmp_path / "scanner_db.json")
    monkeypatch.setattr(routes, "INPUT_DOCS_DIR", source_dir)
    monkeypatch.setattr(routes, "PROCESSED_DOCS_DIR", processed_dir)
    monkeypatch.setattr(routes, "FAILED_FILES_DIR", failed_dir)
    monkeypatch.setattr(routes, "db", test_db)
    monkeypatch.setattr(routes, "settings_table", test_db.table("settings"))
    processed = []

    async def fake_pipeline(transaction_id, filename, content, config):
        processed.append((filename, content))
        return {"status": "completed"}

    monkeypatch.setattr(routes, "run_pipeline_core", fake_pipeline)

    async def run_scan():
        await routes.scan_input_folder()

    asyncio.run(run_scan())
    assert processed == [("report.txt", "Financial report contents.")]
    records = test_db.search(routes.Query().filename == "report.txt")
    assert records[-1]["status"] == "processing"
    assert all(record.get("status") != "queued" for record in records)
    test_db.close()


def test_failed_file_returned_to_source_creates_a_fresh_job(tmp_path, monkeypatch):
    source_dir = tmp_path / "briefing_source"
    processed_dir = tmp_path / "processed_files"
    failed_dir = tmp_path / "failed_files"
    source_dir.mkdir()
    processed_dir.mkdir()
    failed_dir.mkdir()
    source_file = source_dir / "retry.txt"
    source_file.write_text("Retry this report.", encoding="utf-8")

    test_db = TinyDB(tmp_path / "retry_db.json")
    monkeypatch.setattr(routes, "INPUT_DOCS_DIR", source_dir)
    monkeypatch.setattr(routes, "PROCESSED_DOCS_DIR", processed_dir)
    monkeypatch.setattr(routes, "FAILED_FILES_DIR", failed_dir)
    monkeypatch.setattr(routes, "db", test_db)
    monkeypatch.setattr(routes, "settings_table", test_db.table("settings"))

    fingerprint = routes.scanner_fingerprint(source_file)
    test_db.insert({
        "id": "failed-attempt",
        "file_fingerprint": fingerprint,
        "filename": source_file.name,
        "status": "error",
    })
    processed = []

    async def fake_pipeline(transaction_id, filename, content, config):
        processed.append((transaction_id, filename))
        return {"status": "completed"}

    monkeypatch.setattr(routes, "run_pipeline_core", fake_pipeline)

    async def run_scan():
        await routes.scan_input_folder()

    asyncio.run(run_scan())
    attempts = test_db.search(routes.Query().file_fingerprint == fingerprint)
    assert len(attempts) == 2
    assert processed[0][0] != "failed-attempt"
    test_db.close()


def test_successful_pipeline_moves_source_and_writes_flat_artifacts(tmp_path, monkeypatch):
    source_dir = tmp_path / "briefing_source"
    processed_dir = tmp_path / "processed_files"
    failed_dir = tmp_path / "failed_files"
    source_dir.mkdir()
    processed_dir.mkdir()
    failed_dir.mkdir()
    source_file = source_dir / "market_report.txt"
    source_file.write_text("Market report contents.", encoding="utf-8")

    test_db = TinyDB(tmp_path / "workflow_db.json")
    monkeypatch.setattr(routes, "INPUT_DOCS_DIR", source_dir)
    monkeypatch.setattr(routes, "PROCESSED_DOCS_DIR", processed_dir)
    monkeypatch.setattr(routes, "FAILED_FILES_DIR", failed_dir)
    monkeypatch.setattr(routes, "db", test_db)
    monkeypatch.setattr(routes, "settings_table", test_db.table("settings"))

    transaction_id = "workflow-test"
    test_db.insert({
        "id": transaction_id,
        "transaction_id": transaction_id,
        "filename": source_file.name,
        "status": "processing",
        "received_at": "2026-08-31T10:00:00",
    })

    async def fake_invoke(state):
        (state["output_dir"] / state["audio_path"]).write_bytes(b"ID3-test")
        return {
            **state,
            "english_summary": "A short English market summary.",
            "urdu_summary": "ایک مختصر اردو خلاصہ۔",
            "summary_metrics": {
                "usage": {},
                "extracted_data": {"company_name": "Example Limited", "symbol": "EXM"},
                "extracted_name": "Example Limited",
            },
            "translation_metrics": {"usage": {}},
            "audio_metrics": {"characters": 24},
        }

    monkeypatch.setattr(routes, "document_graph", SimpleNamespace(ainvoke=fake_invoke))

    result = asyncio.run(routes.run_pipeline_core(
        transaction_id,
        source_file.name,
        source_file.read_text(encoding="utf-8"),
        PipelineConfig(),
    ))

    assert result["status"] == "completed"
    assert not source_file.exists()
    assert (processed_dir / "market_report.txt").exists()
    assert (processed_dir / "market_report_summary.txt").read_text(encoding="utf-8") == "A short English market summary."
    assert (processed_dir / "market_report_translation.txt").read_text(encoding="utf-8") == "ایک مختصر اردو خلاصہ۔"
    assert (processed_dir / "market_report_audio.mp3").read_bytes() == b"ID3-test"
    assert (processed_dir / "market_report_manifest.json").exists()
    test_db.close()

# tests/test_endpoints.py

from fastapi.testclient import TestClient
from pathlib import Path

# Updated: Import from src.main since we renamed the file
from src.main import app

client = TestClient(app)


def test_health_check():
    """Verifies the API is awake and responding."""
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Briefcast API"}


def test_upload_documents(tmp_path):
    """Simulates a multipart form-data file upload."""

    dummy_file = tmp_path / "test_doc.txt"
    dummy_file.write_text("This is a test document for the Briefcast pipeline.")

    with open(dummy_file, "rb") as f:
        files = {"files": ("test_doc.txt", f, "text/plain")}
        response = client.post("/api/upload-docs", files=files)

    assert response.status_code == 200

    data = response.json()
    assert "Successfully uploaded" in data["message"]
    assert "test_doc.txt" in data["filenames"]

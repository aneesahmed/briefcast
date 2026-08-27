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


def test_upload_openapi_uses_binary_file_picker():
    schema = client.get("/openapi.json").json()
    upload_schema = schema["components"]["schemas"][
        "Body_upload_documents_api_upload_docs_post"
    ]
    file_items = upload_schema["properties"]["files"]["items"]

    assert file_items["type"] == "string"
    assert file_items["format"] == "binary"
    assert "contentMediaType" not in file_items

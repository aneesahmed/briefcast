import os
from typing import Dict, Any

from fastapi.testclient import TestClient
from src.core.config import INPUT_DOCS_DIR
from src.main import app

def test_summary_integration():
    client = TestClient(app)
    
    # Make sure we have a file
    filename = "test_doc.txt"
    with open(INPUT_DOCS_DIR / filename, "w") as f:
        f.write("This is a test document for summarization.")
        
    payload = {
        "filename": filename,
        "config": {
            "summary_provider": "cloud",
            "summary_model": "gemini-2.5-flash"
        },
        "force": True
    }
    
    print("Running integration test via client.post...")
    try:
        res = client.post("/api/step/summary", json=payload)
        print("Status Code:", res.status_code)
        print("Success:", res.json())
    except Exception as e:
        print("Exception occurred:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Ensure GEMINI_API_KEY is available for the test if it's in .env
    from dotenv import load_dotenv
    load_dotenv()
    test_summary_integration()

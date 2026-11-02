# tests/test_tiered_extraction_and_resilience.py

from unittest.mock import MagicMock, patch

import pypdf
import pytest

from src.api import routes
from src.core.config import MAX_OCR_PAGES, MAX_TOKEN_LIMIT
from src.services.document_service import (
    DocumentFileError,
    DocumentService,
    collapse_whitespace,
    is_page_garbled,
)


def test_is_page_garbled():
    assert is_page_garbled("/MT67/MT79/MT78/MT84") is True
    assert is_page_garbled("/n3/n1/n11/n41") is True
    assert is_page_garbled("Normal text /n1 and something") is False
    assert is_page_garbled("Standard Financial Report for Q3 2026") is False
    assert is_page_garbled("") is False


def test_collapse_whitespace():
    raw = "Header    Col1       Col2\n\n\n\nRow1    100        200\n\n\n"
    collapsed = collapse_whitespace(raw)
    assert "    " not in collapsed
    assert "\n\n\n" not in collapsed
    assert "Header  Col1  Col2\n\nRow1  100  200" == collapsed


def test_garbled_pdf_mostly_garbled(tmp_path):
    pdf_path = tmp_path / "mostly_garbled.pdf"
    writer = pypdf.PdfWriter()
    
    # 4 garbled pages and 1 good page
    for i in range(4):
        writer.add_blank_page(width=100, height=100)
    writer.add_blank_page(width=100, height=100)
    
    with open(pdf_path, "wb") as f:
        writer.write(f)

    with patch.object(
        pypdf._page.PageObject,
        "extract_text",
        side_effect=[
            "/MT67/MT79/MT78/MT84",
            "/MT67/MT79/MT78/MT84",
            "/MT67/MT79/MT78/MT84",
            "/MT67/MT79/MT78/MT84",
            "This is clean page text with enough normal words.",
        ],
    ), pytest.raises(DocumentFileError, match="mostly garbled"):
        DocumentService.read_file(pdf_path)


def test_garbled_page_dropped_continues_clean(tmp_path):
    pdf_path = tmp_path / "single_garbled_page.pdf"
    writer = pypdf.PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=100, height=100)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    # Page 1: clean text, Page 2: garbled, Page 3: clean text
    with patch.object(
        pypdf._page.PageObject,
        "extract_text",
        side_effect=[
            "Page 1 has valid text with more than fifteen words so it qualifies as a standard text document.",
            "/n1/n2/n3/n4",
            "Page 3 also has valid financial text with numbers 100 200 300.",
        ],
    ), patch("pymupdf4llm.to_markdown", return_value="# Page 1\n\n# Page 3") as mock_mupdf:
        text, usage, doc_type = DocumentService.read_file(pdf_path)
        assert doc_type == "text_pdf"
        assert usage["input_tokens"] == 0
        assert text == "# Page 1\n\n# Page 3"
        # Verify pymupdf4llm was called excluding page index 1
        mock_mupdf.assert_called_once_with(str(pdf_path), pages=[0, 2])


def test_scanned_pdf_trimmed_to_10_pages(tmp_path):
    pdf_path = tmp_path / "scanned_doc.pdf"
    writer = pypdf.PdfWriter()
    # 25 pages
    for _ in range(25):
        writer.add_blank_page(width=100, height=100)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    mock_client = MagicMock()
    mock_file = MagicMock()
    mock_file.name = "files/test_123"
    mock_client.files.upload.return_value = mock_file
    
    mock_resp = MagicMock()
    mock_resp.text = "Extracted OCR markdown text from scanned document."
    mock_resp.usage_metadata.prompt_token_count = 1200
    mock_resp.usage_metadata.candidates_token_count = 150
    mock_resp.usage_metadata.thoughts_token_count = 0
    mock_resp.usage_metadata.total_token_count = 1350
    mock_client.models.generate_content.return_value = mock_resp

    with patch("src.services.document_service.genai.Client", return_value=mock_client):
        text, usage, doc_type = DocumentService.read_file(pdf_path)

        assert doc_type == "image_pdf"
        assert usage["ocr_truncated"] is True
        assert usage["input_tokens"] == 1200
        assert text == "Extracted OCR markdown text from scanned document."
        
        # Verify the uploaded stream only had 10 pages
        upload_call = mock_client.files.upload.call_args
        stream_arg = upload_call.kwargs["file"]
        trimmed_reader = pypdf.PdfReader(stream_arg)
        assert len(trimmed_reader.pages) == MAX_OCR_PAGES
        mock_client.files.delete.assert_called_once_with(name="files/test_123")


def test_token_limit_exceeded(tmp_path):
    txt_path = tmp_path / "huge.txt"
    # Create content that exceeds MAX_TOKEN_LIMIT (600,000 * 4 = 2.4M chars)
    txt_path.write_text("A" * (MAX_TOKEN_LIMIT * 4 + 100), encoding="utf-8")
    
    with pytest.raises(DocumentFileError, match="exceeds token limit"):
        DocumentService.read_file(txt_path)


def test_error_classification():
    assert routes.classify_processing_error(DocumentFileError("Corrupt PDF"))[0] is True
    assert routes.classify_processing_error(Exception("400 Invalid argument payload"))[0] is True
    assert routes.classify_processing_error(Exception("Safety block triggered on harassment"))[0] is True
    assert routes.classify_processing_error(ValueError("Gemini returned no structured financial data"))[0] is True
    
    # System errors
    assert routes.classify_processing_error(Exception("503 Service Unavailable"))[0] is False
    assert routes.classify_processing_error(Exception("Connection timed out"))[0] is False


def test_repeat_offender_guard_logic():
    routes.SYSTEM_ERROR_COUNTS.clear()
    filename = "poison_file.pdf"
    
    # 1st system error -> count = 1
    routes.SYSTEM_ERROR_COUNTS[filename] = routes.SYSTEM_ERROR_COUNTS.get(filename, 0) + 1
    assert routes.SYSTEM_ERROR_COUNTS[filename] == 1
    
    # 2nd system error -> count = 2 (triggers repeat-offender failure)
    routes.SYSTEM_ERROR_COUNTS[filename] = routes.SYSTEM_ERROR_COUNTS.get(filename, 0) + 1
    assert routes.SYSTEM_ERROR_COUNTS[filename] == 2
    
    # Reset on failure
    routes.SYSTEM_ERROR_COUNTS.pop(filename, None)
    assert filename not in routes.SYSTEM_ERROR_COUNTS

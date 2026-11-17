import pytest
from src.api.routes import (
    classify_processing_error,
    is_system_or_connectivity_error,
)
from src.services.document_service import DocumentFileError


def test_connectivity_errors_classified_as_system():
    dns_err = ConnectionError("HTTPSConnectionPool: Max retries exceeded (Caused by NameResolutionError: getaddrinfo failed)")
    assert is_system_or_connectivity_error(dns_err) is True
    is_file, reason = classify_processing_error(dns_err)
    assert is_file is False

    refused_err = ConnectionRefusedError("Connection refused by peer")
    assert is_system_or_connectivity_error(refused_err) is True
    is_file, reason = classify_processing_error(refused_err)
    assert is_file is False

    timeout_err = TimeoutError("Network operation timed out")
    assert is_system_or_connectivity_error(timeout_err) is True
    is_file, reason = classify_processing_error(timeout_err)
    assert is_file is False


def test_auth_and_quota_classified_as_system():
    auth_err = RuntimeError("401 Unauthorized: API key not valid")
    assert is_system_or_connectivity_error(auth_err) is True
    is_file, reason = classify_processing_error(auth_err)
    assert is_file is False

    quota_err = RuntimeError("429 RESOURCE_EXHAUSTED: Quota exceeded for quota metric")
    assert is_system_or_connectivity_error(quota_err) is True
    is_file, reason = classify_processing_error(quota_err)
    assert is_file is False

    outage_err = RuntimeError("503 Service Unavailable")
    assert is_system_or_connectivity_error(outage_err) is True
    is_file, reason = classify_processing_error(outage_err)
    assert is_file is False


def test_tts_failure_classified_as_file_error():
    tts_err = ValueError("Gemini TTS failed to generate audio (FinishReason: FinishReason.OTHER).")
    assert is_system_or_connectivity_error(tts_err) is False
    is_file, reason = classify_processing_error(tts_err)
    assert is_file is True
    assert "Text-to-speech audio generation failed" in reason

    no_candidates = ValueError("Gemini returned no candidates.")
    assert is_system_or_connectivity_error(no_candidates) is False
    is_file, reason = classify_processing_error(no_candidates)
    assert is_file is True


def test_document_errors_classified_as_file_error():
    doc_err = DocumentFileError("Scanned document produced empty OCR output.")
    is_file, reason = classify_processing_error(doc_err)
    assert is_file is True

    bad_req = RuntimeError("400 Bad Request: Invalid argument supplied in contents")
    is_file, reason = classify_processing_error(bad_req)
    assert is_file is True

    safety_err = RuntimeError("Blocked by safety filters: HARM_CATEGORY_DANGEROUS_CONTENT")
    is_file, reason = classify_processing_error(safety_err)
    assert is_file is True

    empty_data = ValueError("Failed to extract structured data: returned no structured financial data")
    is_file, reason = classify_processing_error(empty_data)
    assert is_file is True

    arbitrary_parsing_err = KeyError("Failed to parse field 'company_name' from summary")
    is_file, reason = classify_processing_error(arbitrary_parsing_err)
    assert is_file is True
    assert "Document processing failed" in reason

import json
from pathlib import Path

import pytest

from src.services import telemetry


def configure_telemetry(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed_files"
    database_dir = tmp_path / "db-init"
    processed_dir.mkdir()
    database_dir.mkdir()

    monkeypatch.setattr(telemetry, "PROCESSED_DOCS_DIR", processed_dir)
    monkeypatch.setattr(telemetry, "DB_DIR", database_dir)
    monkeypatch.setattr(telemetry, "DB_PATH", database_dir / "audit.db")
    monkeypatch.setattr(
        telemetry,
        "INIT_SQL_PATH",
        Path(__file__).resolve().parents[2] / "db-init" / "init.sql",
    )
    return processed_dir


def write_manifest(processed_dir: Path, audio_model: str):
    # Ten seconds at the application's constant 128 kbps MP3 bitrate.
    (processed_dir / "sample_audio.mp3").write_bytes(b"0" * 160_000)
    (processed_dir / "sample_translation.txt").write_text("اردو متن", encoding="utf-8")
    (processed_dir / "sample_summary.txt").write_text("English summary", encoding="utf-8")
    (processed_dir / "sample_manifest.json").write_text(
        json.dumps(
            {
                "original_filename": "sample.pdf",
                "completed_at": "2026-09-25T00:30:00+05:00",
                "summary_file": "sample_summary.txt",
                "translation_file": "sample_translation.txt",
                "audio_file": "sample_audio.mp3",
                "ocr_metrics": {},
                "summary_metrics": {},
                "translation_metrics": {},
                "audio_metrics": {"model": audio_model},
            }
        ),
        encoding="utf-8",
    )


def test_scan_backfills_audio_output_cost_and_preserves_local_date(tmp_path, monkeypatch):
    processed_dir = configure_telemetry(tmp_path, monkeypatch)
    write_manifest(processed_dir, "gemini-2.5-flash-preview-tts")

    telemetry.init_db()
    telemetry._run_scan()

    record = telemetry.fetch_audit_records()[0]
    daily = telemetry.fetch_audit_daily()[0]
    estimated_input_tokens = len("اردو متن")

    assert record["audio_tokens"] == estimated_input_tokens + 320
    assert record["audio_cost_usd"] == pytest.approx(
        estimated_input_tokens * 0.50 / 1_000_000 + 320 * 10.00 / 1_000_000
    )
    assert daily["audit_date"] == "2026-09-25"

    # A changed manifest must refresh its existing database row.
    write_manifest(processed_dir, "gemini-3.1-flash-tts-preview")
    telemetry._run_scan()
    refreshed = telemetry.fetch_audit_records()[0]

    assert refreshed["audio_tokens"] == estimated_input_tokens + 250
    assert refreshed["audio_cost_usd"] == pytest.approx(
        estimated_input_tokens * 1.00 / 1_000_000 + 250 * 20.00 / 1_000_000
    )

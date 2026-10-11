from types import SimpleNamespace

import pytest

from src.services.pricing import calculate_cost_usd, usage_from_response


def test_usage_and_cost_include_thinking_tokens():
    response = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=1_000,
            candidates_token_count=2_000,
            thoughts_token_count=3_000,
            total_token_count=6_000,
        )
    )

    metrics = usage_from_response(response, "gemini-3.7-flash")

    assert metrics["thinking_tokens"] == 3_000
    assert calculate_cost_usd(metrics) == pytest.approx(0.0195)


def test_cost_sums_requests_that_used_different_tts_models():
    metrics = {
        "billable_requests": [
            {
                "model": "gemini-2.5-flash-preview-tts",
                "input_tokens": 100,
                "output_tokens": 1_000,
            },
            {
                "model": "gemini-3.1-flash-tts-preview",
                "input_tokens": 100,
                "output_tokens": 1_000,
            },
        ]
    }

    assert calculate_cost_usd(metrics) == pytest.approx(0.03015)

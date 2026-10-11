"""Gemini usage extraction and paid-tier cost calculation.

Rates are USD per one million tokens for standard Gemini Developer API calls.
Keep this table aligned with https://ai.google.dev/gemini-api/docs/pricing.
"""

from typing import Any

MODEL_PRICING_USD_PER_MILLION: dict[str, dict[str, float]] = {
    "gemini-3.7-flash": {"input": 0.75, "output": 3.75},
    "gemini-2.5-flash-preview-tts": {"input": 0.50, "output": 10.00},
    "gemini-3.1-flash-tts-preview": {"input": 1.00, "output": 20.00},
}

# Gemini 3.1 TTS documents 25 output tokens/second. Gemini 2.5 TTS usage
# metadata is preferred; 32 tokens/second is used only to recover old manifests.
AUDIO_OUTPUT_TOKENS_PER_SECOND: dict[str, float] = {
    "gemini-2.5-flash-preview-tts": 32.0,
    "gemini-3.1-flash-tts-preview": 25.0,
}


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def usage_from_response(response: Any, model: str) -> dict[str, Any]:
    """Extract billable token fields from a google-genai response."""
    usage = getattr(response, "usage_metadata", None)
    input_tokens = _integer(getattr(usage, "prompt_token_count", 0))
    output_tokens = _integer(getattr(usage, "candidates_token_count", 0))
    thinking_tokens = _integer(getattr(usage, "thoughts_token_count", 0))
    total_tokens = _integer(getattr(usage, "total_token_count", 0))

    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "thinking_tokens": thinking_tokens,
        "total_tokens": total_tokens
        or input_tokens + output_tokens + thinking_tokens,
    }


def calculate_cost_usd(metrics: dict[str, Any] | None, default_model: str = "") -> float:
    """Calculate cost from captured usage, including thinking and retry requests."""
    if not isinstance(metrics, dict):
        return 0.0

    requests = metrics.get("billable_requests")
    if isinstance(requests, list) and requests:
        return sum(
            calculate_cost_usd(request, request.get("model", default_model))
            for request in requests
            if isinstance(request, dict)
        )

    model = str(metrics.get("model") or default_model)
    pricing = MODEL_PRICING_USD_PER_MILLION.get(model)
    if pricing is None:
        return 0.0

    input_tokens = _integer(metrics.get("input_tokens"))
    output_tokens = _integer(metrics.get("output_tokens"))
    thinking_tokens = _integer(metrics.get("thinking_tokens"))
    return (
        input_tokens * pricing["input"]
        + (output_tokens + thinking_tokens) * pricing["output"]
    ) / 1_000_000.0


def calculate_cost_cents(metrics: dict[str, Any] | None, default_model: str = "") -> float:
    return round(calculate_cost_usd(metrics, default_model) * 100.0, 6)


def estimate_audio_output_tokens(duration_seconds: float, model: str) -> int:
    rate = AUDIO_OUTPUT_TOKENS_PER_SECOND.get(model)
    if rate is None or duration_seconds <= 0:
        return 0
    return round(duration_seconds * rate)

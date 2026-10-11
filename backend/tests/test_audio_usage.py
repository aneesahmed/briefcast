import asyncio
from types import SimpleNamespace

from src.services import agent_graph


def test_audio_node_records_response_usage_and_active_model(tmp_path, monkeypatch):
    response = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=20,
            candidates_token_count=250,
            thoughts_token_count=0,
            total_token_count=270,
        ),
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[SimpleNamespace(inline_data=SimpleNamespace(data=b"pcm"))]
                )
            )
        ],
    )

    class FakeModels:
        async def generate_content(self, **_kwargs):
            return response

    client = SimpleNamespace(aio=SimpleNamespace(models=FakeModels()))
    monkeypatch.setattr(agent_graph, "get_gemini_client", lambda: client)
    monkeypatch.setattr(
        agent_graph,
        "write_mp3",
        lambda pcm_bytes, output_file, _sample_rate: output_file.write_bytes(pcm_bytes),
    )
    monkeypatch.setattr(agent_graph, "_flash_audio_quota_reset_time", 0.0)

    result = asyncio.run(
        agent_graph.generate_audio_node(
            {
                "urdu_summary": "مختصر خبر",
                "output_dir": tmp_path,
                "audio_path": "sample.mp3",
                "pipeline_config": {
                    "audio_model": "gemini-2.5-flash-preview-tts",
                    "audio_provider": "cloud",
                },
            }
        )
    )

    metrics = result["audio_metrics"]
    assert metrics["input_tokens"] == 20
    assert metrics["output_tokens"] == 250
    assert metrics["model"] == "gemini-2.5-flash-preview-tts"
    assert metrics["billable_requests"][0]["total_tokens"] == 270

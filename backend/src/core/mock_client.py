import os
from pathlib import Path

class DummyInlineData:
    def __init__(self, data: bytes):
        self.data = data

class DummyPart:
    def __init__(self, data: bytes):
        self.inline_data = DummyInlineData(data)

class DummyContent:
    def __init__(self, data: bytes):
        self.parts = [DummyPart(data)]

class DummyCandidate:
    def __init__(self, data: bytes):
        self.content = DummyContent(data)

class DummyAudioResponse:
    def __init__(self, data: bytes):
        self.candidates = [DummyCandidate(data)]

class DummyTextResponse:
    def __init__(self, text: str, parsed=None):
        self.text = text
        self.parsed = parsed

class MockModels:
    def generate_content(self, model: str, contents, config=None, **kwargs):
        config_str = str(config)
        if "application/json" in config_str:
            from src.models import FinancialReportExtraction
            parsed = FinancialReportExtraction(
                document_classification="Dummy Report",
                company_name="Dummy Company",
                symbol="DUMMY",
                reporting_period="Q1",
                currency_scale="Millions",
                key_metrics=[],
                corporate_actions=None
            )
            return DummyTextResponse('{"company_name": "Dummy Company"}', parsed)
        else:
            if "translate" in str(contents).lower():
                return DummyTextResponse("dummy translation for func test")
            return DummyTextResponse("dummy summary for functional testing")

class MockAsyncModels:
    async def generate_content(self, model: str, contents, config=None, **kwargs):
        config_str = str(config)
        if "AUDIO" in config_str:
            dummy_mp3_path = Path(__file__).resolve().parent.parent.parent / "assets" / "dummy_audio.mp3"
            with open(dummy_mp3_path, "rb") as f:
                return DummyAudioResponse(f.read())
        return DummyTextResponse("dummy async response")

class MockAio:
    def __init__(self):
        self.models = MockAsyncModels()

class MockGeminiClient:
    """A mock client that mimics google.genai.Client for local testing."""
    def __init__(self, *args, **kwargs):
        self.models = MockModels()
        self.aio = MockAio()

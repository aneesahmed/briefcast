import asyncio
from pathlib import Path
from pydantic import BaseModel
from typing import Any
from src.services.document_service import DocumentService
from src.services.agent_graph import get_gemini_client
from google.genai import types
from src.core.config import SUMMARY_MODEL
from src.models import FinancialMetric, CorporateAction

class EnhancedExtraction(BaseModel):
    title: str | None = None
    company_name: str
    symbol: str | None = None
    broadcast_callname: str
    reporting_period: str
    currency_scale: str
    key_metrics: list[FinancialMetric]
    corporate_actions: CorporateAction | None = None

def extract_financial_data_enhanced(text: str, model: str) -> dict[str, Any]:
    response = get_gemini_client().models.generate_content(
        model=model,
        contents=[
            text,
            "Extract the title, formal company name, stock symbol when present, and a conversational broadcast_callname (e.g. strip away 'Limited', 'Inc', and make it sound natural on air). Also extract financial results and corporate actions.",
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=EnhancedExtraction,
            temperature=0.0,
        ),
    )
    if hasattr(response.parsed, 'model_dump'):
        return response.parsed.model_dump()
    return dict(response.parsed)

def main():
    processed_dir = Path("C:/working/AI26/briefcast/processed_files")
    pdfs = list(processed_dir.glob("*.pdf"))[:5]
    
    for pdf in pdfs:
        print(f"\n--- Testing {pdf.name} ---")
        text = DocumentService.read_file(pdf)
        extracted = extract_financial_data_enhanced(text, SUMMARY_MODEL)
        print(f"Company:  {extracted.get('company_name')}")
        print(f"Symbol:   {extracted.get('symbol')}")
        print(f"Title:    {extracted.get('title')}")
        print(f"Callname: {extracted.get('broadcast_callname')}")

if __name__ == '__main__':
    main()

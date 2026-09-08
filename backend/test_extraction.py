import asyncio
from pathlib import Path
from src.services.document_service import DocumentService
from src.services.agent_graph import extract_financial_data
from src.core.config import SUMMARY_MODEL
import json

def main():
    processed_dir = Path("C:/working/AI26/briefcast/processed_files")
    pdfs = list(processed_dir.glob("*.pdf"))[:5]
    
    for pdf in pdfs:
        print(f"\n--- Testing {pdf.name} ---")
        try:
            text = DocumentService.read_file(pdf)
            extracted = extract_financial_data(text, SUMMARY_MODEL)
            print(f"Company: {extracted.get('company_name')}")
            print(f"Symbol:  {extracted.get('symbol')}")
            print(f"Title:   {extracted.get('title')}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == '__main__':
    main()

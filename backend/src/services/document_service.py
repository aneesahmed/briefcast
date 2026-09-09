# src/services/document_service.py

from pathlib import Path

import docx
import pypdf

from src.core.config import (
    DOCX_DOCUMENT_EXTENSION,
    PDF_DOCUMENT_EXTENSION,
    TEXT_DOCUMENT_EXTENSION,
)


class DocumentService:
    @staticmethod
    def read_file(file_path: Path) -> str:
        """Extract text from one supported TXT, PDF, or DOCX document."""
        ext = file_path.suffix.lower()
        if ext == TEXT_DOCUMENT_EXTENSION:
            return file_path.read_text(encoding="utf-8")
            
        if ext == PDF_DOCUMENT_EXTENSION:
            reader = pypdf.PdfReader(file_path)
            text = "\n".join(
                page_text
                for page in reader.pages
                if (page_text := page.extract_text())
            ).strip()
            
            # If text is present, return it immediately
            if text:
                return text
                
            # If no text was found (image-only PDF), use Gemini File API to read the scanned document
            import os
            from google import genai
            from src.core.config import SUMMARY_MODEL
            
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            uploaded_file = client.files.upload(file=str(file_path))
            try:
                response = client.models.generate_content(
                    model=SUMMARY_MODEL,
                    contents=[
                        uploaded_file, 
                        "Extract all readable text from this scanned document exactly as written."
                    ],
                )
                return response.text.strip() if response.text else ""
            finally:
                client.files.delete(name=uploaded_file.name)
                
        if ext == DOCX_DOCUMENT_EXTENSION:
            document = docx.Document(file_path)
            return "\n".join(
                paragraph.text
                for paragraph in document.paragraphs
                if paragraph.text.strip()
            ).strip()
        raise ValueError(
            f"Unsupported document type '{ext or 'unknown'}'. Use TXT, PDF, or DOCX."
        )

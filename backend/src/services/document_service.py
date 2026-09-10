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
    def read_file(file_path: Path) -> tuple[str, dict, str]:
        """Extract text from one supported TXT, PDF, or DOCX document."""
        ext = file_path.suffix.lower()
        if ext == TEXT_DOCUMENT_EXTENSION:
            return file_path.read_text(encoding="utf-8"), {"input_tokens": 0, "output_tokens": 0}, "text"
            
        if ext == PDF_DOCUMENT_EXTENSION:
            with file_path.open("rb") as f:
                reader = pypdf.PdfReader(f)
                text = "\n".join(
                    page_text
                    for page in reader.pages
                    if (page_text := page.extract_text())
                ).strip()
            
            # If the extracted text is substantial (more than 15 words), return it.
            # Otherwise (e.g. if it just says "CamScanner" or page numbers), treat it as an image-only PDF.
            if len(text.split()) > 15:
                return text, {"input_tokens": 0, "output_tokens": 0}, "text_pdf"
                
            # If no text was found (image-only PDF), use Gemini File API to read the scanned document
            import os
            from google import genai
            from src.settings import OCR_MODEL
            
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            uploaded_file = client.files.upload(file=str(file_path))
            try:
                from google.genai import types
                response = client.models.generate_content(
                    model=OCR_MODEL,
                    contents=[
                        uploaded_file, 
                        "Extract only the English text from this scanned document. Ignore any Urdu, Arabic, or other languages. Output only the extracted English text."
                    ],
                    config=types.GenerateContentConfig(
                        thinking_config=types.ThinkingConfig(thinking_level="LOW")
                    ),
                )
                usage = {
                    "input_tokens": getattr(response.usage_metadata, "prompt_token_count", 0) if getattr(response, "usage_metadata", None) else 0,
                    "output_tokens": getattr(response.usage_metadata, "candidates_token_count", 0) if getattr(response, "usage_metadata", None) else 0
                }
                text_content = response.text.strip() if response.text else ""
                return text_content, usage, "image_pdf"
            finally:
                client.files.delete(name=uploaded_file.name)
                
        if ext == DOCX_DOCUMENT_EXTENSION:
            document = docx.Document(file_path)
            text_content = "\n".join(
                paragraph.text
                for paragraph in document.paragraphs
                if paragraph.text.strip()
            ).strip()
            return text_content, {"input_tokens": 0, "output_tokens": 0}, "docx"
        raise ValueError(
            f"Unsupported document type '{ext or 'unknown'}'. Use TXT, PDF, or DOCX."
        )

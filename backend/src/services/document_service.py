# src/services/document_service.py

import os
from pathlib import Path
from zipfile import BadZipFile

import docx
import pypdf
from docx.opc.exceptions import PackageNotFoundError
from google import genai
from google.genai import types

from src.core.config import (
    DOCX_DOCUMENT_EXTENSION,
    PDF_DOCUMENT_EXTENSION,
    TEXT_DOCUMENT_EXTENSION,
)
from src.services.pricing import usage_from_response
from src.settings import OCR_MODEL


class DocumentFileError(ValueError):
    """The source document itself is invalid, corrupt, or unreadable."""


class DocumentService:
    @staticmethod
    def read_file(file_path: Path) -> tuple[str, dict, str]:
        """Extract text from one supported TXT, PDF, or DOCX document."""
        ext = file_path.suffix.lower()
        if ext == TEXT_DOCUMENT_EXTENSION:
            try:
                text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise DocumentFileError(
                    f"{file_path.name} is not a valid UTF-8 text file."
                ) from exc
            return text, {"input_tokens": 0, "output_tokens": 0}, "text"
            
        if ext == PDF_DOCUMENT_EXTENSION:
            try:
                with file_path.open("rb") as f:
                    reader = pypdf.PdfReader(f)
                    text = "\n".join(
                        page_text
                        for page in reader.pages
                        if (page_text := page.extract_text())
                    ).strip()
            except pypdf.errors.PdfReadError as exc:
                raise DocumentFileError(
                    f"{file_path.name} is not a valid readable PDF."
                ) from exc
            
            # If the extracted text is substantial (more than 15 words), return it.
            # Otherwise (e.g. if it just says "CamScanner" or page numbers), treat it as an image-only PDF.
            if len(text.split()) > 15:
                return text, {"input_tokens": 0, "output_tokens": 0}, "text_pdf"
                
            # If no text was found (image-only PDF), use Gemini File API to read the scanned document
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            uploaded_file = client.files.upload(file=str(file_path))
            try:
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
                usage = usage_from_response(response, OCR_MODEL)
                text_content = response.text.strip() if response.text else ""
                return text_content, usage, "image_pdf"
            finally:
                client.files.delete(name=uploaded_file.name)
                
        if ext == DOCX_DOCUMENT_EXTENSION:
            try:
                document = docx.Document(file_path)
            except (BadZipFile, PackageNotFoundError) as exc:
                raise DocumentFileError(
                    f"{file_path.name} is not a valid readable DOCX file."
                ) from exc
            text_content = "\n".join(
                paragraph.text
                for paragraph in document.paragraphs
                if paragraph.text.strip()
            ).strip()
            return text_content, {"input_tokens": 0, "output_tokens": 0}, "docx"
        raise DocumentFileError(
            f"Unsupported document type '{ext or 'unknown'}'. Use TXT, PDF, or DOCX."
        )

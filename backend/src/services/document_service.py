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
            return "\n".join(
                page_text
                for page in reader.pages
                if (page_text := page.extract_text())
            ).strip()
        if ext == DOCX_DOCUMENT_EXTENSION:
            document = docx.Document(file_path)
            return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
        raise ValueError(
            f"Unsupported document type '{ext or 'unknown'}'. Use TXT, PDF, or DOCX."
        )

# src/services/document_service.py

from pathlib import Path
from typing import Dict

import docx
import pypdf


class DocumentService:
    @staticmethod
    def read_file(file_path: Path) -> str:
        """Extract text from one supported TXT, PDF, or DOCX document."""
        ext = file_path.suffix.lower()
        if ext == ".txt":
            return file_path.read_text(encoding="utf-8")
        if ext == ".pdf":
            reader = pypdf.PdfReader(file_path)
            return "\n".join(
                page_text
                for page in reader.pages
                if (page_text := page.extract_text())
            ).strip()
        if ext == ".docx":
            document = docx.Document(file_path)
            return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
        raise ValueError(
            f"Unsupported document type '{ext or 'unknown'}'. Use TXT, PDF, or DOCX."
        )

    @staticmethod
    def read_folder(folder_path: str) -> Dict[str, str]:
        """
        Scans a directory and extracts text from PDF, DOCX, and TXT files.
        Returns a dictionary mapping filename to extracted text.
        """
        results = {}
        path = Path(folder_path)

        if not path.exists() or not path.is_dir():
            raise ValueError(f"Directory not found: {folder_path}")

        for file_path in path.glob("*"):
            if not file_path.is_file():
                continue

            filename = file_path.name

            try:
                results[filename] = DocumentService.read_file(file_path)

            except ValueError:
                continue
            except Exception as e:
                # Matches the error handling expected by announcement.py
                results[filename] = f"Error extracting {filename}: {str(e)}"

        return results

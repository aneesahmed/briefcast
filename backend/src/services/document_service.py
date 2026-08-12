# src/services/document_service.py

from pathlib import Path
from typing import Dict

import docx
import pypdf


class DocumentService:
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

            ext = file_path.suffix.lower()
            filename = file_path.name

            try:
                if ext == ".txt":
                    with open(file_path, "r", encoding="utf-8") as f:
                        results[filename] = f.read()

                elif ext == ".pdf":
                    text = ""
                    reader = pypdf.PdfReader(file_path)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                    results[filename] = text.strip()

                elif ext == ".docx":
                    doc = docx.Document(file_path)
                    text = "\n".join([para.text for para in doc.paragraphs])
                    results[filename] = text.strip()

            except Exception as e:
                # Matches the error handling expected by announcement.py
                results[filename] = f"Error extracting {filename}: {str(e)}"

        return results
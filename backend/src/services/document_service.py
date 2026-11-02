# src/services/document_service.py

import io
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import BadZipFile

import docx
import pypdf
from docx.opc.exceptions import PackageNotFoundError
from google import genai
from google.genai import types

from src.core.config import (
    DOCX_DOCUMENT_EXTENSION,
    EXTRACT_WORKERS,
    MAX_OCR_PAGES,
    MAX_TOKEN_LIMIT,
    MIN_CONTENT_WORDS,
    MIN_FILE_SIZE_BYTES,
    PAGE_TIER_CUTOFF,
    PDF_DOCUMENT_EXTENSION,
    TEXT_DOCUMENT_EXTENSION,
)
from src.services.pricing import usage_from_response
from src.settings import OCR_MODEL

logger = logging.getLogger("briefcast.document")

GARBLE_PATTERN = re.compile(
    r"(?:(?:/[a-zA-Z]{1,5}\d+|\ufffd|CID:\d+)[,\s]*){4,}",
    re.IGNORECASE,
)


class DocumentFileError(ValueError):
    """The source document itself is invalid, corrupt, or unreadable."""


def is_page_garbled(text: str) -> bool:
    """Check if page text contains 4 or more consecutive unmapped glyph tokens."""
    if not text or not text.strip():
        return False
    return bool(GARBLE_PATTERN.search(text))


def collapse_whitespace(text: str) -> str:
    """Collapse 3+ whitespace runs and 3+ blank lines to conserve tokens."""
    text = re.sub(r"[ \t]{3,}", "  ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class DocumentService:
    @staticmethod
    def read_file(file_path: Path) -> tuple[str, dict, str]:
        """Extract text from one supported TXT, PDF, or DOCX document."""
        if not file_path.exists():
            raise DocumentFileError(f"{file_path.name} does not exist.")

        file_size = file_path.stat().st_size
        ext = file_path.suffix.lower()
        min_size = MIN_FILE_SIZE_BYTES.get(ext, 100)
        if file_size < min_size:
            raise DocumentFileError(
                f"{file_path.name} is too small ({file_size} bytes). Minimum required for {ext.upper() or 'file'} is {min_size} bytes."
            )

        if ext == TEXT_DOCUMENT_EXTENSION:
            try:
                text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise DocumentFileError(
                    f"{file_path.name} is not a valid UTF-8 text file."
                ) from exc
            word_count = len(text.split())
            if word_count < MIN_CONTENT_WORDS:
                raise DocumentFileError(
                    f"{file_path.name} contains insufficient content ({word_count} words). Minimum required is {MIN_CONTENT_WORDS} words."
                )
            estimated_tokens = len(text) // 4
            if estimated_tokens > MAX_TOKEN_LIMIT:
                raise DocumentFileError(
                    f"{file_path.name} exceeds token limit (~{estimated_tokens:,} tokens > {MAX_TOKEN_LIMIT:,})."
                )
            return text, {"input_tokens": 0, "output_tokens": 0, "ocr_truncated": False}, "text"
            
        if ext == PDF_DOCUMENT_EXTENSION:
            try:
                with file_path.open("rb") as f:
                    reader = pypdf.PdfReader(f)
                    
                    # Pre-flight: Check encryption
                    if reader.is_encrypted:
                        raise DocumentFileError(f"{file_path.name} is password protected/encrypted.")
                    
                    total_pages = len(reader.pages)
                    if total_pages == 0:
                        raise DocumentFileError(f"{file_path.name} contains no pages.")
                    
                    # Pre-flight: Per-page garble check
                    garbled_pages: set[int] = set()
                    raw_extracted_pages: list[str] = []
                    
                    for idx, page in enumerate(reader.pages):
                        try:
                            page_text = page.extract_text() or ""
                        except Exception:
                            page_text = ""
                        
                        if is_page_garbled(page_text):
                            garbled_pages.add(idx)
                            logger.warning(
                                "Dropped garbled page %d of %d in %s",
                                idx + 1,
                                total_pages,
                                file_path.name,
                            )
                        else:
                            raw_extracted_pages.append(page_text)
                    
                    # If most pages are garbled, fail the document cleanly
                    if len(garbled_pages) > 0 and (len(garbled_pages) / total_pages) > 0.5:
                        raise DocumentFileError(
                            f"{file_path.name} is mostly garbled ({len(garbled_pages)} of {total_pages} pages contain corrupt font encoding)."
                        )
                    
                    valid_page_indices = [
                        i for i in range(total_pages) if i not in garbled_pages
                    ]
                    
                    combined_raw_text = "\n".join(raw_extracted_pages).strip()
                    raw_words_count = len(combined_raw_text.split())
                    
                    # Image-only / Scanned PDF path (15 words or fewer)
                    if raw_words_count <= 15:
                        pages_to_ocr = min(total_pages, MAX_OCR_PAGES)
                        is_truncated = total_pages > MAX_OCR_PAGES
                        
                        logger.info(
                            "OCR'd pages 1-%d of %d for scanned PDF %s",
                            pages_to_ocr,
                            total_pages,
                            file_path.name,
                        )
                        
                        writer = pypdf.PdfWriter()
                        for p_idx in range(pages_to_ocr):
                            writer.add_page(reader.pages[p_idx])
                            
                        pdf_stream = io.BytesIO()
                        writer.write(pdf_stream)
                        pdf_stream.seek(0)
                        
                        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
                        uploaded_file = client.files.upload(
                            file=pdf_stream,
                            config=types.UploadFileConfig(
                                mime_type="application/pdf",
                                display_name=file_path.name,
                            ),
                        )
                        try:
                            response = client.models.generate_content(
                                model=OCR_MODEL,
                                contents=[
                                    uploaded_file, 
                                    "Extract only the English text from this scanned document into clean Markdown format with tables. "
                                    "Ignore any Urdu, Arabic, or other languages. Output only the extracted English Markdown text."
                                ],
                                config=types.GenerateContentConfig(
                                    thinking_config=types.ThinkingConfig(thinking_level="LOW")
                                ),
                            )
                            usage = usage_from_response(response, OCR_MODEL)
                            usage["ocr_truncated"] = is_truncated
                            text_content = response.text.strip() if response.text else ""
                            if not text_content:
                                raise DocumentFileError(
                                    f"Scanned document {file_path.name} produced empty OCR output."
                                )
                            ocr_words = len(text_content.split())
                            if ocr_words < MIN_CONTENT_WORDS:
                                raise DocumentFileError(
                                    f"Scanned document {file_path.name} produced insufficient text from OCR ({ocr_words} words). Minimum required is {MIN_CONTENT_WORDS} words."
                                )
                            return text_content, usage, "image_pdf"
                        finally:
                            try:
                                client.files.delete(name=uploaded_file.name)
                            except Exception:
                                pass

                    # Text-based PDF path (clean text > 15 words)
                    if len(valid_page_indices) <= PAGE_TIER_CUTOFF:
                        # Tier 1: Clean text PDFs <= PAGE_TIER_CUTOFF using pymupdf4llm for Markdown + tables
                        try:
                            import pymupdf4llm
                            text_content = pymupdf4llm.to_markdown(
                                str(file_path),
                                pages=valid_page_indices,
                            )
                        except Exception as mupdf_err:
                            logger.warning(
                                "pymupdf4llm extraction failed for %s (%s); falling back to pypdf layout",
                                file_path.name,
                                mupdf_err,
                            )
                            text_content = "\n\n".join(
                                reader.pages[i].extract_text(extraction_mode="layout") or ""
                                for i in valid_page_indices
                            )
                    else:
                        # Tier 2: Longer PDFs > PAGE_TIER_CUTOFF using pypdf layout mode
                        if EXTRACT_WORKERS > 1:
                            def _extract_page_layout(p_idx: int) -> str:
                                return reader.pages[p_idx].extract_text(extraction_mode="layout") or ""
                            
                            with ThreadPoolExecutor(max_workers=EXTRACT_WORKERS) as executor:
                                page_results = list(executor.map(_extract_page_layout, valid_page_indices))
                            text_content = "\n\n".join(page_results)
                        else:
                            text_content = "\n\n".join(
                                reader.pages[i].extract_text(extraction_mode="layout") or ""
                                for i in valid_page_indices
                            )
                    
                    # Collapse blank lines and whitespace runs to save tokens
                    text_content = collapse_whitespace(text_content)
                    
                    # Pre-flight token limit and content word checks
                    word_count = len(text_content.split())
                    if word_count < MIN_CONTENT_WORDS:
                        raise DocumentFileError(
                            f"{file_path.name} contains insufficient content ({word_count} words). Minimum required is {MIN_CONTENT_WORDS} words."
                        )
                    estimated_tokens = len(text_content) // 4
                    if estimated_tokens > MAX_TOKEN_LIMIT:
                        raise DocumentFileError(
                            f"{file_path.name} exceeds token limit (~{estimated_tokens:,} tokens > {MAX_TOKEN_LIMIT:,})."
                        )
                    
                    return text_content, {"input_tokens": 0, "output_tokens": 0, "ocr_truncated": False}, "text_pdf"

            except DocumentFileError:
                raise
            except pypdf.errors.PdfReadError as exc:
                raise DocumentFileError(
                    f"{file_path.name} is not a valid readable PDF."
                ) from exc
                
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
            word_count = len(text_content.split())
            if word_count < MIN_CONTENT_WORDS:
                raise DocumentFileError(
                    f"{file_path.name} contains insufficient content ({word_count} words). Minimum required is {MIN_CONTENT_WORDS} words."
                )
            estimated_tokens = len(text_content) // 4
            if estimated_tokens > MAX_TOKEN_LIMIT:
                raise DocumentFileError(
                    f"{file_path.name} exceeds token limit (~{estimated_tokens:,} tokens > {MAX_TOKEN_LIMIT:,})."
                )
            return text_content, {"input_tokens": 0, "output_tokens": 0, "ocr_truncated": False}, "docx"
            
        raise DocumentFileError(
            f"Unsupported document type '{ext or 'unknown'}'. Use TXT, PDF, or DOCX."
        )

import os
import logging
from typing import List, Dict, Any
import pypdf

logger = logging.getLogger(__name__)


class ParsedPage:
    def __init__(self, page_number: int, text: str):
        self.page_number = page_number
        self.text = text


class DocumentParser:
    """Multi-format document parsing engine extracting structured text with page attribution."""

    @staticmethod
    def parse_file(file_path: str, file_type: str) -> List[ParsedPage]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at {file_path}")

        ext = file_type.lower().replace(".", "")
        if ext == "pdf" or "pdf" in ext:
            return DocumentParser._parse_pdf(file_path)
        elif ext in ["docx", "doc"] or "word" in ext:
            return DocumentParser._parse_docx(file_path)
        elif ext in ["txt", "md", "markdown", "text"]:
            return DocumentParser._parse_text(file_path)
        else:
            # Fallback to plain text reading
            return DocumentParser._parse_text(file_path)

    @staticmethod
    def _parse_pdf(file_path: str) -> List[ParsedPage]:
        pages = []
        try:
            reader = pypdf.PdfReader(file_path)
            for idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                cleaned = DocumentParser._clean_text(text)
                if cleaned:
                    pages.append(ParsedPage(page_number=idx + 1, text=cleaned))
        except Exception as e:
            logger.error(f"Error reading PDF {file_path}: {e}")
            raise
        
        if not pages:
            raise ValueError(f"No extractable text found in PDF {file_path}")
        return pages

    @staticmethod
    def _parse_docx(file_path: str) -> List[ParsedPage]:
        try:
            import docx2txt
            full_text = docx2txt.process(file_path)
            cleaned = DocumentParser._clean_text(full_text)
            if not cleaned:
                raise ValueError(f"Empty DOCX document at {file_path}")
            # DOCX has no discrete pages by default without full renderer, assign page 1
            return [ParsedPage(page_number=1, text=cleaned)]
        except Exception as e:
            logger.error(f"Error reading DOCX {file_path}: {e}")
            raise

    @staticmethod
    def _parse_text(file_path: str) -> List[ParsedPage]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            cleaned = DocumentParser._clean_text(content)
            if not cleaned:
                raise ValueError(f"Empty text file at {file_path}")
            return [ParsedPage(page_number=1, text=cleaned)]
        except Exception as e:
            logger.error(f"Error reading text file {file_path}: {e}")
            raise

    @staticmethod
    def _clean_text(text: str) -> str:
        """Strip control characters and excessive empty lines while preserving paragraphs."""
        if not text:
            return ""
        lines = [line.strip() for line in text.splitlines()]
        # Remove consecutive empty lines
        cleaned_lines = []
        last_empty = False
        for line in lines:
            if not line:
                if not last_empty:
                    cleaned_lines.append("")
                    last_empty = True
            else:
                cleaned_lines.append(line)
                last_empty = False
        return "\n".join(cleaned_lines).strip()

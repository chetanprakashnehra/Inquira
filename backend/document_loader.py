from datetime import datetime, timezone
from pathlib import Path
import json

from pypdf import PdfReader
from docx import Document as DocxDocument


class DocumentLoader:

    SUPPORTED_TYPES = {
        ".txt",
        ".pdf",
        ".json",
        ".docx",
    }

    def load(self, file_path: str) -> dict:

        path = Path(file_path)
        extension = path.suffix.lower()

        if extension not in self.SUPPORTED_TYPES:
            raise ValueError(
                f"Unsupported file type: {extension}"
            )

        if extension == ".txt":
            documents = self._load_txt(path)

        elif extension == ".pdf":
            documents = self._load_pdf(path)

        elif extension == ".json":
            documents = self._load_json(path)

        elif extension == ".docx":
            documents = self._load_docx(path)

        return {
            "documents": documents,
            "metadata": {
                "source": path.name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "file_type": extension.lstrip("."),
            },
        }

    def _load_txt(self, path: Path) -> list:
        text = path.read_text(encoding="utf-8")

        return [
            {
                "text": text,
                "metadata": {
                    "page": None
                }
            }
        ]

    def _load_pdf(self, path: Path) -> list:
        reader = PdfReader(str(path))

        documents = []

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""

            if text.strip():
                documents.append(
                    {
                        "text": text,
                        "metadata": {
                            "page": page_number
                        }
                    }
                )

        return documents

    def _load_json(self, path: Path) -> list:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )

        text = json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        )

        return [
            {
                "text": text,
                "metadata": {
                    "page": None
                }
            }
        ]

    def _load_docx(self, path: Path) -> list:
        document = DocxDocument(str(path))

        paragraphs = []

        for paragraph in document.paragraphs:
            if paragraph.text.strip():
                paragraphs.append(paragraph.text)

        text = "\n\n".join(paragraphs)

        return [
            {
                "text": text,
                "metadata": {
                    "page": None
                }
            }
        ]
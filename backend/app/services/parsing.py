import io
import logging
from dataclasses import dataclass
from pathlib import Path

import docx
import fitz
import pytesseract
from PIL import Image

from app.core.config import settings
from app.models import Document
from app.services import storage

logger = logging.getLogger(__name__)

_OCR_RENDER_DPI = 200


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str
    source: str


def _ocr_page(page) -> str:
    pix = page.get_pixmap(dpi=_OCR_RENDER_DPI)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(image).strip()


def extract_pdf(path: Path) -> list[ExtractedPage]:
    pages: list[ExtractedPage] = []
    with fitz.open(path) as pdf:
        for ordinal, page in enumerate(pdf, start=1):
            native = page.get_text("text").strip()
            if native:
                pages.append(ExtractedPage(ordinal, native, "native_pdf"))
            else:
                pages.append(ExtractedPage(ordinal, _ocr_page(page), "ocr_pdf"))
    return pages


def extract_docx(path: Path) -> list[ExtractedPage]:
    document = docx.Document(path)
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    text = "\n\n".join(paragraphs)
    return [ExtractedPage(1, text, "docx")]


def extract_text(path: Path) -> list[ExtractedPage]:
    text = path.read_text(encoding="utf-8")
    return [ExtractedPage(1, text, "text")]


def extract(document: Document) -> list[ExtractedPage]:
    path = settings.upload_dir / document.stored_filename
    if not path.exists():
        raise FileNotFoundError(f"stored file missing for document_id={document.id}")
    extension = storage.extension_for(document.stored_filename)
    if extension == ".pdf":
        return extract_pdf(path)
    if extension == ".docx":
        return extract_docx(path)
    if extension in {".txt", ".md"}:
        return extract_text(path)
    raise ValueError(f"unsupported extension for extraction: {extension}")

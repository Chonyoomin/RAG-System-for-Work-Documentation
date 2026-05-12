import hashlib
import zipfile
from pathlib import Path

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"

_DOCX_REQUIRED_ENTRIES = {"[Content_Types].xml", "word/document.xml"}


def extension_for(filename: str) -> str:
    return Path(filename).suffix.lower()


def is_allowed(filename: str) -> bool:
    return extension_for(filename) in ALLOWED_EXTENSIONS


def compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stored_filename_for(content_hash: str, extension: str) -> str:
    return f"{content_hash}{extension}"


def validate_docx_structure(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
    except zipfile.BadZipFile:
        return "DOCX is not a valid ZIP archive"
    missing = _DOCX_REQUIRED_ENTRIES - names
    if missing:
        return f"DOCX missing required entries: {sorted(missing)}"
    return None

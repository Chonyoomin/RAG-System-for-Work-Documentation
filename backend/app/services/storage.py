import hashlib
from pathlib import Path

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"


def extension_for(filename: str) -> str:
    return Path(filename).suffix.lower()


def is_allowed(filename: str) -> bool:
    return extension_for(filename) in ALLOWED_EXTENSIONS


def compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stored_filename_for(content_hash: str, extension: str) -> str:
    return f"{content_hash}{extension}"


def write_bytes(root: Path, stored_filename: str, data: bytes) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    target = root / stored_filename
    target.write_bytes(data)
    return target


def _looks_like_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def validate_content(extension: str, data: bytes) -> str | None:
    if extension == ".pdf":
        if not data.startswith(_PDF_MAGIC):
            return "missing PDF signature (expected '%PDF-')"
    elif extension == ".docx":
        if not data.startswith(_ZIP_MAGIC):
            return "missing DOCX/ZIP signature (expected 'PK\\x03\\x04')"
    elif extension in {".txt", ".md"}:
        if not _looks_like_text(data):
            return "not valid UTF-8 text or contains NUL bytes"
    return None

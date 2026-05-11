import hashlib
from pathlib import Path

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


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

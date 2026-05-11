import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Document
from app.services import storage

logger = logging.getLogger(__name__)


class UnsupportedFileType(Exception):
    def __init__(self, extension: str):
        super().__init__(extension)
        self.extension = extension


class DuplicateDocument(Exception):
    def __init__(self, existing: Document):
        super().__init__(existing.content_hash)
        self.existing = existing


def ingest(session: Session, original_filename: str, data: bytes) -> Document:
    if not storage.is_allowed(original_filename):
        raise UnsupportedFileType(storage.extension_for(original_filename) or "<none>")

    content_hash = storage.compute_hash(data)
    existing = session.query(Document).filter_by(content_hash=content_hash).one_or_none()
    if existing is not None:
        logger.info("duplicate upload rejected hash=%s existing_id=%s", content_hash[:8], existing.id)
        raise DuplicateDocument(existing)

    extension = storage.extension_for(original_filename)
    stored_filename = storage.stored_filename_for(content_hash, extension)
    storage.write_bytes(settings.upload_dir, stored_filename, data)

    document = Document(
        original_filename=original_filename,
        stored_filename=stored_filename,
        mime_type=storage.MIME_BY_EXTENSION[extension],
        size_bytes=len(data),
        content_hash=content_hash,
        status="uploaded",
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    logger.info(
        "ingested document id=%s hash=%s name=%s size=%d",
        document.id, content_hash[:8], original_filename, len(data),
    )
    return document

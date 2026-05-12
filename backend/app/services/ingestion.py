import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Document
from app.services import storage

logger = logging.getLogger(__name__)


class UnsupportedFileType(Exception):
    def __init__(self, extension: str):
        super().__init__(extension)
        self.extension = extension


class InvalidFileContent(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class FileTooLarge(Exception):
    def __init__(self, size: int, limit: int):
        super().__init__(f"{size} > {limit}")
        self.size = size
        self.limit = limit


class DuplicateDocument(Exception):
    def __init__(self, existing: Document):
        super().__init__(existing.content_hash)
        self.existing = existing


def ingest(session: Session, original_filename: str, data: bytes) -> Document:
    if len(data) > settings.max_upload_bytes:
        raise FileTooLarge(len(data), settings.max_upload_bytes)

    if not storage.is_allowed(original_filename):
        raise UnsupportedFileType(storage.extension_for(original_filename) or "<none>")

    extension = storage.extension_for(original_filename)
    invalid_reason = storage.validate_content(extension, data)
    if invalid_reason:
        raise InvalidFileContent(invalid_reason)

    content_hash = storage.compute_hash(data)

    existing = session.query(Document).filter_by(content_hash=content_hash).one_or_none()
    if existing is not None:
        logger.info("duplicate (pre-check) hash=%s existing_id=%s", content_hash[:8], existing.id)
        raise DuplicateDocument(existing)

    stored_filename = storage.stored_filename_for(content_hash, extension)
    file_path = storage.write_bytes(settings.upload_dir, stored_filename, data)

    document = Document(
        original_filename=original_filename,
        stored_filename=stored_filename,
        mime_type=storage.MIME_BY_EXTENSION[extension],
        size_bytes=len(data),
        content_hash=content_hash,
        status="uploaded",
    )
    session.add(document)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        winner = session.query(Document).filter_by(content_hash=content_hash).one()
        # The DB row is the source of truth for which file is owned.
        # If the winner stored under a different extension, our file is at a different
        # path than winner.stored_filename and is orphaned -- delete it.
        if winner.stored_filename != stored_filename:
            file_path.unlink(missing_ok=True)
        logger.info("duplicate (race) hash=%s existing_id=%s", content_hash[:8], winner.id)
        raise DuplicateDocument(winner)
    except Exception:
        # Non-integrity DB failure: pre-check passed and no race row exists, so our file
        # is genuinely orphaned. Remove it before propagating.
        session.rollback()
        file_path.unlink(missing_ok=True)
        raise

    session.refresh(document)
    logger.info(
        "ingested document id=%s hash=%s name=%s size=%d",
        document.id, content_hash[:8], original_filename, len(data),
    )
    return document

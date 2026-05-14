import logging
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Document
from app.services import storage

logger = logging.getLogger(__name__)


class DuplicateDocument(Exception):
    def __init__(self, existing: Document):
        super().__init__(existing.content_hash)
        self.existing = existing


def persist_upload(
    session: Session,
    *,
    original_filename: str,
    tmp_path: Path,
    extension: str,
    content_hash: str,
    size_bytes: int,
) -> Document:
    existing = session.query(Document).filter_by(content_hash=content_hash).one_or_none()
    if existing is not None:
        logger.info("duplicate (pre-check) hash=%s existing_id=%s", content_hash[:8], existing.id)
        raise DuplicateDocument(existing)

    stored_filename = storage.stored_filename_for(content_hash, extension)
    final_path = settings.upload_dir / stored_filename
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.replace(final_path)

    document = Document(
        original_filename=original_filename,
        stored_filename=stored_filename,
        mime_type=storage.MIME_BY_EXTENSION[extension],
        size_bytes=size_bytes,
        content_hash=content_hash,
        status="uploaded",
    )
    session.add(document)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        winner = session.query(Document).filter_by(content_hash=content_hash).one()
        # DB row is the source of truth for which file path is owned. If the winner
        # stored under a different extension, our just-promoted file is orphaned.
        if winner.stored_filename != stored_filename:
            final_path.unlink(missing_ok=True)
        logger.info("duplicate (race) hash=%s existing_id=%s", content_hash[:8], winner.id)
        raise DuplicateDocument(winner)
    except Exception:
        session.rollback()
        final_path.unlink(missing_ok=True)
        raise

    session.refresh(document)
    logger.info(
        "ingested document id=%s hash=%s name=%s size=%d",
        document.id, content_hash[:8], original_filename, size_bytes,
    )
    return document

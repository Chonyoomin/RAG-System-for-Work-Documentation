import logging
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Document, Page
from app.services import parsing

logger = logging.getLogger(__name__)

STATUS_UPLOADED = "uploaded"
STATUS_EXTRACTED = "extracted"
STATUS_EXTRACTION_FAILED = "extraction_failed"


class ExtractionError(Exception):
    pass


@dataclass
class ExtractionResult:
    page_count: int
    sources: dict[str, int]


def extract_and_persist(session: Session, document: Document) -> ExtractionResult:
    # Parse first; only touch existing pages once we know we have a successful result.
    try:
        extracted = parsing.extract(document)
    except Exception as exc:
        document.status = STATUS_EXTRACTION_FAILED
        session.commit()
        logger.exception("extraction failed document_id=%s", document.id)
        raise ExtractionError(str(exc)) from exc

    if not extracted:
        document.status = STATUS_EXTRACTION_FAILED
        session.commit()
        raise ExtractionError("no pages extracted")

    # Atomic replace inside a single commit: prior pages are kept until we're sure the
    # new extraction landed cleanly.
    session.query(Page).filter_by(document_id=document.id).delete()
    for ep in extracted:
        session.add(Page(
            document_id=document.id,
            page_number=ep.page_number,
            text=ep.text,
            source=ep.source,
        ))
    document.status = STATUS_EXTRACTED
    session.commit()
    session.refresh(document)

    sources = dict(Counter(ep.source for ep in extracted))
    logger.info(
        "extracted document_id=%s pages=%d sources=%s",
        document.id, len(extracted), sources,
    )
    return ExtractionResult(page_count=len(extracted), sources=sources)

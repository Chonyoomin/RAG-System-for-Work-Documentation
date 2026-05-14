import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Chunk, Document, Page

logger = logging.getLogger(__name__)

STATUS_EXTRACTED = "extracted"
STATUS_CHUNKED = "chunked"


class ChunkingError(Exception):
    pass


@dataclass(frozen=True)
class PlannedChunk:
    page_id: int
    page_number: int
    chunk_index: int
    char_start: int
    char_end: int
    text: str


@dataclass
class ChunkingResult:
    chunk_count: int
    page_count: int


def chunk_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[tuple[int, int, str]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and < chunk_size")
    if not text:
        return []
    if len(text) <= chunk_size:
        return [(0, len(text), text)]
    step = chunk_size - chunk_overlap
    windows: list[tuple[int, int, str]] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        windows.append((start, end, text[start:end]))
        if end == n:
            break
        start += step
    return windows


def plan_chunks(pages: list[Page], *, chunk_size: int, chunk_overlap: int) -> list[PlannedChunk]:
    planned: list[PlannedChunk] = []
    for page in pages:
        windows = chunk_text(page.text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        for idx, (start, end, body) in enumerate(windows):
            planned.append(PlannedChunk(
                page_id=page.id,
                page_number=page.page_number,
                chunk_index=idx,
                char_start=start,
                char_end=end,
                text=body,
            ))
    return planned


def chunk_and_persist(session: Session, document: Document) -> ChunkingResult:
    if document.status not in {STATUS_EXTRACTED, STATUS_CHUNKED}:
        raise ChunkingError(
            f"document must be extracted before chunking (status={document.status})"
        )

    pages = (
        session.query(Page)
        .filter_by(document_id=document.id)
        .order_by(Page.page_number)
        .all()
    )
    if not pages:
        raise ChunkingError("no extracted pages to chunk")

    planned = plan_chunks(
        pages,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    if not planned:
        raise ChunkingError("pages produced no chunks")

    session.query(Chunk).filter_by(document_id=document.id).delete()
    for pc in planned:
        session.add(Chunk(
            document_id=document.id,
            page_id=pc.page_id,
            page_number=pc.page_number,
            chunk_index=pc.chunk_index,
            char_start=pc.char_start,
            char_end=pc.char_end,
            text=pc.text,
        ))
    document.status = STATUS_CHUNKED
    session.commit()
    session.refresh(document)

    logger.info(
        "chunked document_id=%s pages=%d chunks=%d size=%d overlap=%d",
        document.id, len(pages), len(planned),
        settings.chunk_size, settings.chunk_overlap,
    )
    return ChunkingResult(chunk_count=len(planned), page_count=len(pages))

import logging
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Chunk, ChunkEmbedding, Document
from app.models.embedding import EMBEDDING_DIM
from app.services import embedding

logger = logging.getLogger(__name__)

STATUS_CHUNKED = "chunked"
STATUS_INDEXED = "indexed"


class IndexingError(Exception):
    pass


@dataclass
class IndexingResult:
    chunk_count: int
    indexed_count: int
    embedding_model: str
    embedding_dim: int


@dataclass
class IndexingCoverage:
    chunk_count: int
    indexed_count: int
    is_fully_indexed: bool
    embedding_models: list[dict] = field(default_factory=list)


def coverage(session: Session, document: Document) -> IndexingCoverage:
    chunk_count = session.query(Chunk).filter_by(document_id=document.id).count()
    grouped = (
        session.query(
            ChunkEmbedding.embedding_model,
            ChunkEmbedding.embedding_dim,
            func.count(ChunkEmbedding.id).label("n"),
        )
        .filter(ChunkEmbedding.document_id == document.id)
        .group_by(ChunkEmbedding.embedding_model, ChunkEmbedding.embedding_dim)
        .order_by(ChunkEmbedding.embedding_model)
        .all()
    )
    embedding_models = [
        {
            "embedding_model": row.embedding_model,
            "indexed_count": int(row.n),
            "embedding_dim": int(row.embedding_dim),
        }
        for row in grouped
    ]
    active = embedding.EMBEDDING_MODEL
    indexed_count = next(
        (m["indexed_count"] for m in embedding_models if m["embedding_model"] == active),
        0,
    )
    is_fully_indexed = chunk_count > 0 and indexed_count == chunk_count
    return IndexingCoverage(
        chunk_count=chunk_count,
        indexed_count=indexed_count,
        is_fully_indexed=is_fully_indexed,
        embedding_models=embedding_models,
    )


def index_document(session: Session, document: Document) -> IndexingResult:
    if document.status not in {STATUS_CHUNKED, STATUS_INDEXED}:
        raise IndexingError(
            f"document must be chunked before indexing (status={document.status})"
        )

    chunks = (
        session.query(Chunk)
        .filter_by(document_id=document.id)
        .order_by(Chunk.page_number, Chunk.chunk_index)
        .all()
    )
    if not chunks:
        raise IndexingError("no chunks to index")

    model_name = embedding.EMBEDDING_MODEL
    vectors = embedding.embedder.embed_texts([c.text for c in chunks])
    if len(vectors) != len(chunks):
        raise IndexingError(
            f"embedder returned {len(vectors)} vectors for {len(chunks)} chunks"
        )
    for v in vectors:
        if len(v) != EMBEDDING_DIM:
            raise IndexingError(
                f"embedder returned dim {len(v)}, schema requires {EMBEDDING_DIM}"
            )

    # Idempotent replace scoped to this (document, model) pair so other models'
    # embeddings for the same chunks remain intact.
    (
        session.query(ChunkEmbedding)
        .filter_by(document_id=document.id, embedding_model=model_name)
        .delete()
    )
    for chunk, vector in zip(chunks, vectors):
        session.add(ChunkEmbedding(
            document_id=document.id,
            page_id=chunk.page_id,
            chunk_id=chunk.id,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
            embedding_model=model_name,
            embedding_dim=EMBEDDING_DIM,
            embedding=list(vector),
        ))
    document.status = STATUS_INDEXED
    session.commit()
    session.refresh(document)

    logger.info(
        "indexed document_id=%s chunks=%d model=%s dim=%d",
        document.id, len(chunks), model_name, EMBEDDING_DIM,
    )
    return IndexingResult(
        chunk_count=len(chunks),
        indexed_count=len(chunks),
        embedding_model=model_name,
        embedding_dim=EMBEDDING_DIM,
    )

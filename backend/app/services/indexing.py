import logging
from dataclasses import dataclass

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

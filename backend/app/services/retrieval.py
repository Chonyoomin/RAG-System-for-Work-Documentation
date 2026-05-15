import logging
import math
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Chunk, ChunkEmbedding, Document
from app.models.embedding import EMBEDDING_DIM
from app.services import embedding

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5
MAX_TOP_K = 50


class RetrievalError(Exception):
    pass


@dataclass
class RetrievedChunk:
    document_id: int
    page_id: int
    page_number: int
    chunk_id: int
    chunk_index: int
    char_start: int
    char_end: int
    text: str
    score: float
    distance: float
    embedding_model: str
    original_filename: str


@dataclass
class RetrievalResult:
    query: str
    embedding_model: str
    embedding_dim: int
    top_k: int
    results: list[RetrievedChunk]


def retrieve(session: Session, *, query: str, top_k: int = DEFAULT_TOP_K) -> RetrievalResult:
    if not query or not query.strip():
        raise RetrievalError("query is empty")
    if top_k <= 0 or top_k > MAX_TOP_K:
        raise RetrievalError(f"top_k must be in [1, {MAX_TOP_K}]")

    model_name = embedding.EMBEDDING_MODEL
    indexed_rows = (
        session.query(ChunkEmbedding)
        .filter_by(embedding_model=model_name)
        .count()
    )
    if indexed_rows == 0:
        raise RetrievalError(f"no indexed chunks for model={model_name}")

    vectors = embedding.embedder.embed_texts([query])
    if not vectors or len(vectors[0]) != EMBEDDING_DIM:
        raise RetrievalError(
            f"embedder returned dim {len(vectors[0]) if vectors else 0}, "
            f"schema requires {EMBEDDING_DIM}"
        )
    query_vector = list(vectors[0])

    results = _vector_search(session, query_vector, model_name, top_k)
    logger.info(
        "retrieved query_len=%d hits=%d model=%s top_k=%d",
        len(query), len(results), model_name, top_k,
    )
    return RetrievalResult(
        query=query,
        embedding_model=model_name,
        embedding_dim=EMBEDDING_DIM,
        top_k=top_k,
        results=results,
    )


def _vector_search(
    session: Session, vector: list[float], model_name: str, top_k: int
) -> list[RetrievedChunk]:
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "postgresql":
        return _vector_search_pgvector(session, vector, model_name, top_k)
    return _vector_search_python_fallback(session, vector, model_name, top_k)


def _vector_search_pgvector(
    session: Session, vector: list[float], model_name: str, top_k: int
) -> list[RetrievedChunk]:
    distance = ChunkEmbedding.embedding.cosine_distance(vector).label("distance")
    rows = (
        session.query(ChunkEmbedding, Chunk, Document, distance)
        .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
        .join(Document, Document.id == ChunkEmbedding.document_id)
        .filter(ChunkEmbedding.embedding_model == model_name)
        .order_by(distance.asc(), ChunkEmbedding.chunk_id.asc())
        .limit(top_k)
        .all()
    )
    out: list[RetrievedChunk] = []
    for emb, chunk, doc, dist in rows:
        d = float(dist)
        out.append(RetrievedChunk(
            document_id=emb.document_id,
            page_id=emb.page_id,
            page_number=emb.page_number,
            chunk_id=emb.chunk_id,
            chunk_index=emb.chunk_index,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            text=chunk.text,
            score=1.0 - d,
            distance=d,
            embedding_model=emb.embedding_model,
            original_filename=doc.original_filename,
        ))
    return out


# Narrowly scoped fallback for non-Postgres dialects (test SQLite). Production
# retrieval always uses the pgvector path above; this exists so the fast suite
# can exercise the assembly + ranking shape without a Postgres dependency.
def _vector_search_python_fallback(
    session: Session, vector: list[float], model_name: str, top_k: int
) -> list[RetrievedChunk]:
    rows = (
        session.query(ChunkEmbedding, Chunk, Document)
        .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
        .join(Document, Document.id == ChunkEmbedding.document_id)
        .filter(ChunkEmbedding.embedding_model == model_name)
        .all()
    )
    scored: list[tuple[float, ChunkEmbedding, Chunk, Document]] = []
    for emb, chunk, doc in rows:
        sim = _cosine_similarity(vector, list(emb.embedding))
        scored.append((sim, emb, chunk, doc))
    scored.sort(key=lambda t: (-t[0], t[1].chunk_id))
    top = scored[:top_k]
    return [
        RetrievedChunk(
            document_id=emb.document_id,
            page_id=emb.page_id,
            page_number=emb.page_number,
            chunk_id=emb.chunk_id,
            chunk_index=emb.chunk_index,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            text=chunk.text,
            score=sim,
            distance=1.0 - sim,
            embedding_model=emb.embedding_model,
            original_filename=doc.original_filename,
        )
        for (sim, emb, chunk, doc) in top
    ]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)

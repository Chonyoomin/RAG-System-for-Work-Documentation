import io

import pytest
from fastapi.testclient import TestClient

from app.db import session as session_module
from app.main import app
from app.models import Chunk, ChunkEmbedding
from app.models.embedding import EMBEDDING_DIM
from app.services import embedding, indexing

client = TestClient(app)


def _stub_embedder(monkeypatch, *, dim: int = EMBEDDING_DIM, fixed_value: float | None = None):
    """Replace the global embedder with a deterministic stub.

    Each text gets a vector with one element per dim. ``fixed_value`` lets a
    test pin every element if it doesn't care about content; otherwise we use
    a hash-derived value so the same text always maps to the same vector
    (deterministic re-index assertion).
    """
    def fake(texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            if fixed_value is not None:
                v = fixed_value
            else:
                v = (hash(text) % 1000) / 1000.0
            out.append([v] * dim)
        return out
    monkeypatch.setattr(embedding.embedder, "embed_texts", fake)


def _upload_text(filename: str, content: str, content_type: str = "text/plain") -> int:
    files = {"file": (filename, io.BytesIO(content.encode("utf-8")), content_type)}
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def _upload_extract_chunk(filename: str, content: str) -> int:
    doc_id = _upload_text(filename, content)
    assert client.post(f"/documents/{doc_id}/extract").status_code == 200
    assert client.post(f"/documents/{doc_id}/chunk").status_code == 200
    return doc_id


def test_index_returns_404_for_unknown_document():
    assert client.post("/documents/9999/index").status_code == 404


def test_index_rejects_unchunked_document_with_409(monkeypatch):
    _stub_embedder(monkeypatch)
    doc_id = _upload_text("pending.txt", "synthetic body")
    response = client.post(f"/documents/{doc_id}/index")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "indexing_failed"


def test_index_chunked_document_writes_one_embedding_per_chunk(monkeypatch):
    _stub_embedder(monkeypatch)
    doc_id = _upload_extract_chunk("note.txt", "synthetic body for indexing test")

    response = client.post(f"/documents/{doc_id}/index")
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["status"] == "indexed"
    assert body["embedding_model"] == embedding.EMBEDDING_MODEL
    assert body["embedding_dim"] == EMBEDDING_DIM
    assert body["chunk_count"] == body["indexed_count"] >= 1

    session = session_module.SessionLocal()
    try:
        chunk_count = session.query(Chunk).filter_by(document_id=doc_id).count()
        emb_count = session.query(ChunkEmbedding).filter_by(document_id=doc_id).count()
        assert emb_count == chunk_count == body["chunk_count"]
    finally:
        session.close()


def test_indexed_rows_carry_correct_provenance(monkeypatch):
    _stub_embedder(monkeypatch)
    doc_id = _upload_extract_chunk("prov.txt", "synthetic provenance content")
    client.post(f"/documents/{doc_id}/index")

    session = session_module.SessionLocal()
    try:
        chunks = {
            c.id: c for c in session.query(Chunk).filter_by(document_id=doc_id).all()
        }
        rows = session.query(ChunkEmbedding).filter_by(document_id=doc_id).all()
        assert rows
        for row in rows:
            chunk = chunks[row.chunk_id]
            assert row.document_id == doc_id
            assert row.page_id == chunk.page_id
            assert row.page_number == chunk.page_number
            assert row.chunk_index == chunk.chunk_index
            assert row.embedding_model == embedding.EMBEDDING_MODEL
            assert row.embedding_dim == EMBEDDING_DIM
            assert len(row.embedding) == EMBEDDING_DIM
    finally:
        session.close()


def test_repeat_indexing_is_deterministic_and_does_not_duplicate(monkeypatch):
    _stub_embedder(monkeypatch)
    doc_id = _upload_extract_chunk("idem.txt", "synthetic body for re-index determinism")

    first = client.post(f"/documents/{doc_id}/index").json()
    second = client.post(f"/documents/{doc_id}/index").json()
    assert first["chunk_count"] == second["chunk_count"]
    assert first["indexed_count"] == second["indexed_count"]

    session = session_module.SessionLocal()
    try:
        rows = (
            session.query(ChunkEmbedding)
            .filter_by(document_id=doc_id, embedding_model=embedding.EMBEDDING_MODEL)
            .all()
        )
        assert len(rows) == first["indexed_count"]
        per_chunk = {}
        for r in rows:
            per_chunk.setdefault(r.chunk_id, 0)
            per_chunk[r.chunk_id] += 1
        assert all(count == 1 for count in per_chunk.values())
    finally:
        session.close()


def test_reindex_replaces_only_same_model_rows(monkeypatch):
    _stub_embedder(monkeypatch)
    doc_id = _upload_extract_chunk("multi.txt", "synthetic body for multi-model isolation")
    client.post(f"/documents/{doc_id}/index")

    session = session_module.SessionLocal()
    try:
        chunk = session.query(Chunk).filter_by(document_id=doc_id).first()
        assert chunk is not None
        session.add(ChunkEmbedding(
            document_id=doc_id,
            page_id=chunk.page_id,
            chunk_id=chunk.id,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
            embedding_model="other-model",
            embedding_dim=EMBEDDING_DIM,
            embedding=[0.0] * EMBEDDING_DIM,
        ))
        session.commit()
    finally:
        session.close()

    client.post(f"/documents/{doc_id}/index")

    session = session_module.SessionLocal()
    try:
        other = (
            session.query(ChunkEmbedding)
            .filter_by(document_id=doc_id, embedding_model="other-model")
            .count()
        )
        primary = (
            session.query(ChunkEmbedding)
            .filter_by(document_id=doc_id, embedding_model=embedding.EMBEDDING_MODEL)
            .count()
        )
        assert other == 1, "other-model row must survive a re-index of the primary model"
        assert primary >= 1
    finally:
        session.close()


def test_index_rejects_dim_mismatch_from_embedder(monkeypatch):
    _stub_embedder(monkeypatch, dim=EMBEDDING_DIM - 1, fixed_value=0.0)
    doc_id = _upload_extract_chunk("baddim.txt", "synthetic body for dim mismatch path")

    response = client.post(f"/documents/{doc_id}/index")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "indexing_failed"
    assert "dim" in detail["reason"]


def test_index_status_transitions_chunked_to_indexed(monkeypatch):
    _stub_embedder(monkeypatch)
    doc_id = _upload_extract_chunk("status.txt", "synthetic")
    pre = client.get(f"/documents/{doc_id}").json()
    assert pre["status"] == "chunked"

    client.post(f"/documents/{doc_id}/index")
    post = client.get(f"/documents/{doc_id}").json()
    assert post["status"] == "indexed"


def test_listing_embeddings_returns_provenance_only(monkeypatch):
    _stub_embedder(monkeypatch)
    doc_id = _upload_extract_chunk("list.txt", "synthetic content for embeddings listing")
    client.post(f"/documents/{doc_id}/index")

    rows = client.get(f"/documents/{doc_id}/embeddings").json()
    assert rows
    keys = set(rows[0].keys())
    assert keys == {"chunk_id", "page_number", "chunk_index", "embedding_model", "embedding_dim"}
    assert all(r["embedding_model"] == embedding.EMBEDDING_MODEL for r in rows)


def test_embedder_embed_texts_returns_empty_for_empty_input():
    assert embedding.embedder.embed_texts([]) == []

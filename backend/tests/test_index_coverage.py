import io

from fastapi.testclient import TestClient

from app.db import session as session_module
from app.main import app
from app.models import Chunk, ChunkEmbedding
from app.models.embedding import EMBEDDING_DIM
from app.services import embedding

client = TestClient(app)


def _stub_embedder(monkeypatch):
    def fake(texts: list[str]) -> list[list[float]]:
        return [[0.1] * EMBEDDING_DIM for _ in texts]
    monkeypatch.setattr(embedding.embedder, "embed_texts", fake)


def _upload_text(filename: str, content: str) -> int:
    files = {"file": (filename, io.BytesIO(content.encode("utf-8")), "text/plain")}
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def _upload_extract_chunk(filename: str, content: str) -> int:
    doc_id = _upload_text(filename, content)
    assert client.post(f"/documents/{doc_id}/extract").status_code == 200
    assert client.post(f"/documents/{doc_id}/chunk").status_code == 200
    return doc_id


def test_coverage_returns_404_for_unknown_document():
    assert client.get("/documents/9999/index").status_code == 404


def test_chunked_but_not_indexed_reports_zero_coverage():
    doc_id = _upload_extract_chunk("note.txt", "synthetic body for coverage test")
    response = client.get(f"/documents/{doc_id}/index")
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == doc_id
    assert body["status"] == "chunked"
    assert body["chunk_count"] >= 1
    assert body["indexed_count"] == 0
    assert body["is_fully_indexed"] is False
    assert body["embedding_models"] == []


def test_fully_indexed_document_reports_full_coverage(monkeypatch):
    _stub_embedder(monkeypatch)
    doc_id = _upload_extract_chunk("full.txt", "synthetic body for full coverage")
    client.post(f"/documents/{doc_id}/index")

    body = client.get(f"/documents/{doc_id}/index").json()
    assert body["status"] == "indexed"
    assert body["chunk_count"] >= 1
    assert body["indexed_count"] == body["chunk_count"]
    assert body["is_fully_indexed"] is True
    assert len(body["embedding_models"]) == 1
    only = body["embedding_models"][0]
    assert only["embedding_model"] == embedding.EMBEDDING_MODEL
    assert only["indexed_count"] == body["chunk_count"]
    assert only["embedding_dim"] == EMBEDDING_DIM


def test_partially_indexed_document_reports_not_fully_indexed(monkeypatch):
    """Index, then delete one embedding row to simulate partial coverage."""
    _stub_embedder(monkeypatch)
    doc_id = _upload_extract_chunk(
        "part.txt", ("x" * 1500)  # > chunk_size so we get >=2 chunks
    )
    client.post(f"/documents/{doc_id}/index")

    session = session_module.SessionLocal()
    try:
        chunk_count = session.query(Chunk).filter_by(document_id=doc_id).count()
        assert chunk_count >= 2, "test setup needs >=2 chunks"
        one = session.query(ChunkEmbedding).filter_by(
            document_id=doc_id, embedding_model=embedding.EMBEDDING_MODEL
        ).first()
        session.delete(one)
        session.commit()
    finally:
        session.close()

    body = client.get(f"/documents/{doc_id}/index").json()
    assert body["chunk_count"] == chunk_count
    assert body["indexed_count"] == chunk_count - 1
    assert body["is_fully_indexed"] is False
    assert body["embedding_models"][0]["indexed_count"] == chunk_count - 1


def test_multiple_embedding_models_are_reported(monkeypatch):
    _stub_embedder(monkeypatch)
    doc_id = _upload_extract_chunk("multi.txt", "synthetic body for multi-model coverage")
    client.post(f"/documents/{doc_id}/index")

    session = session_module.SessionLocal()
    try:
        chunks = session.query(Chunk).filter_by(document_id=doc_id).all()
        for chunk in chunks:
            session.add(ChunkEmbedding(
                document_id=doc_id,
                page_id=chunk.page_id,
                chunk_id=chunk.id,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                embedding_model="another-model",
                embedding_dim=EMBEDDING_DIM,
                embedding=[0.0] * EMBEDDING_DIM,
            ))
        session.commit()
    finally:
        session.close()

    body = client.get(f"/documents/{doc_id}/index").json()
    names = {m["embedding_model"] for m in body["embedding_models"]}
    assert names == {embedding.EMBEDDING_MODEL, "another-model"}
    # is_fully_indexed reflects the active model only.
    assert body["is_fully_indexed"] is True
    counts = {m["embedding_model"]: m["indexed_count"] for m in body["embedding_models"]}
    assert counts[embedding.EMBEDDING_MODEL] == body["chunk_count"]
    assert counts["another-model"] == body["chunk_count"]


def test_coverage_response_does_not_expose_raw_vectors(monkeypatch):
    _stub_embedder(monkeypatch)
    doc_id = _upload_extract_chunk("novec.txt", "synthetic")
    client.post(f"/documents/{doc_id}/index")

    body = client.get(f"/documents/{doc_id}/index").json()
    assert "embedding" not in body
    for model_row in body["embedding_models"]:
        assert "embedding" not in model_row
        assert set(model_row.keys()) == {"embedding_model", "indexed_count", "embedding_dim"}


def test_zero_chunk_document_reports_not_fully_indexed():
    doc_id = _upload_text("nochunks.txt", "synthetic")
    body = client.get(f"/documents/{doc_id}/index").json()
    assert body["chunk_count"] == 0
    assert body["indexed_count"] == 0
    assert body["is_fully_indexed"] is False
    assert body["embedding_models"] == []

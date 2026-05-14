import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db import session as session_module
from app.db.base import Base
from app.main import app
from app.models import Chunk, ChunkEmbedding, Document, Page

client = TestClient(app)


def _seed_chunked_document() -> tuple[int, int, int]:
    files = {"file": ("note.txt", io.BytesIO(b"synthetic body for embedding tests"), "text/plain")}
    upload = client.post("/documents/upload", files=files)
    assert upload.status_code == 201, upload.json()
    doc_id = upload.json()["id"]

    assert client.post(f"/documents/{doc_id}/extract").status_code == 200
    assert client.post(f"/documents/{doc_id}/chunk").status_code == 200

    session = session_module.SessionLocal()
    try:
        page = session.query(Page).filter_by(document_id=doc_id).order_by(Page.page_number).first()
        chunk = session.query(Chunk).filter_by(document_id=doc_id).order_by(Chunk.chunk_index).first()
        assert page is not None and chunk is not None
        return doc_id, page.id, chunk.id
    finally:
        session.close()


def test_chunk_embeddings_registered_on_metadata():
    assert ChunkEmbedding.__tablename__ == "chunk_embeddings"
    assert "chunk_embeddings" in Base.metadata.tables

    columns = {c.name for c in Base.metadata.tables["chunk_embeddings"].columns}
    assert {
        "id",
        "document_id",
        "page_id",
        "chunk_id",
        "page_number",
        "chunk_index",
        "embedding_model",
        "embedding_dim",
        "embedding",
        "created_at",
        "updated_at",
    } <= columns


def test_chunk_embeddings_foreign_keys_target_documents_pages_chunks():
    table = Base.metadata.tables["chunk_embeddings"]
    fk_targets = {
        next(iter(col.foreign_keys)).column.table.name
        for col in table.columns
        if col.foreign_keys
    }
    assert {"documents", "pages", "chunks"} <= fk_targets


def test_chunk_embeddings_cascade_delete_from_each_parent():
    table = Base.metadata.tables["chunk_embeddings"]
    for col_name in ("document_id", "page_id", "chunk_id"):
        fk = next(iter(table.c[col_name].foreign_keys))
        assert fk.ondelete == "CASCADE", f"{col_name} must cascade-delete"


def test_chunk_embeddings_unique_on_chunk_and_model():
    table = Base.metadata.tables["chunk_embeddings"]
    uniques = [
        tuple(sorted(c.name for c in con.columns))
        for con in table.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("chunk_id", "embedding_model") in uniques


def test_can_insert_and_read_back_embedding_row():
    doc_id, page_id, chunk_id = _seed_chunked_document()
    vector = [0.1] * settings.embedding_dim

    session = session_module.SessionLocal()
    try:
        row = ChunkEmbedding(
            document_id=doc_id,
            page_id=page_id,
            chunk_id=chunk_id,
            page_number=1,
            chunk_index=0,
            embedding_model="synthetic-test-model",
            embedding_dim=settings.embedding_dim,
            embedding=vector,
        )
        session.add(row)
        session.commit()
        session.refresh(row)

        assert row.id is not None
        assert row.embedding_model == "synthetic-test-model"
        assert row.embedding_dim == settings.embedding_dim
        assert list(row.embedding) == vector
    finally:
        session.close()


def test_duplicate_chunk_model_pair_violates_unique_constraint():
    doc_id, page_id, chunk_id = _seed_chunked_document()
    vector = [0.0] * settings.embedding_dim

    session = session_module.SessionLocal()
    try:
        session.add(ChunkEmbedding(
            document_id=doc_id, page_id=page_id, chunk_id=chunk_id,
            page_number=1, chunk_index=0,
            embedding_model="model-a", embedding_dim=settings.embedding_dim,
            embedding=vector,
        ))
        session.commit()

        session.add(ChunkEmbedding(
            document_id=doc_id, page_id=page_id, chunk_id=chunk_id,
            page_number=1, chunk_index=0,
            embedding_model="model-a", embedding_dim=settings.embedding_dim,
            embedding=vector,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    finally:
        session.close()


def test_same_chunk_can_hold_embeddings_from_different_models():
    doc_id, page_id, chunk_id = _seed_chunked_document()
    vector = [0.0] * settings.embedding_dim

    session = session_module.SessionLocal()
    try:
        session.add(ChunkEmbedding(
            document_id=doc_id, page_id=page_id, chunk_id=chunk_id,
            page_number=1, chunk_index=0,
            embedding_model="model-a", embedding_dim=settings.embedding_dim,
            embedding=vector,
        ))
        session.add(ChunkEmbedding(
            document_id=doc_id, page_id=page_id, chunk_id=chunk_id,
            page_number=1, chunk_index=0,
            embedding_model="model-b", embedding_dim=settings.embedding_dim,
            embedding=vector,
        ))
        session.commit()

        rows = (
            session.query(ChunkEmbedding)
            .filter_by(chunk_id=chunk_id)
            .order_by(ChunkEmbedding.embedding_model)
            .all()
        )
        assert [r.embedding_model for r in rows] == ["model-a", "model-b"]
    finally:
        session.close()


def test_deleting_chunk_cascades_to_embeddings():
    doc_id, page_id, chunk_id = _seed_chunked_document()
    vector = [0.0] * settings.embedding_dim

    session = session_module.SessionLocal()
    try:
        session.add(ChunkEmbedding(
            document_id=doc_id, page_id=page_id, chunk_id=chunk_id,
            page_number=1, chunk_index=0,
            embedding_model="model-a", embedding_dim=settings.embedding_dim,
            embedding=vector,
        ))
        session.commit()
        # Force SQLite to honor FK cascades for this connection.
        session.execute(__import__("sqlalchemy").text("PRAGMA foreign_keys = ON"))
        session.query(Chunk).filter_by(id=chunk_id).delete()
        session.commit()

        remaining = session.query(ChunkEmbedding).filter_by(chunk_id=chunk_id).count()
        assert remaining == 0
    finally:
        session.close()

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Query

from app.core.config import settings
from app.db import session as session_module
from app.main import app
from app.models import Document
from app.services import ingestion, storage

client = TestClient(app)


def _upload(filename: str, payload: bytes, content_type: str = "application/octet-stream"):
    files = {"file": (filename, io.BytesIO(payload), content_type)}
    return client.post("/documents/upload", files=files)


def test_upload_valid_text_file_returns_201_with_metadata():
    payload = b"hello synthetic world"
    response = _upload("note.txt", payload, "text/plain")
    assert response.status_code == 201
    body = response.json()
    assert body["original_filename"] == "note.txt"
    assert body["mime_type"] == "text/plain"
    assert body["size_bytes"] == len(payload)
    assert body["status"] == "uploaded"
    assert len(body["content_hash"]) == 64
    assert body["stored_filename"].endswith(".txt")


def test_upload_accepts_pdf_with_valid_signature():
    payload = b"%PDF-1.4\nfake body but signature is valid"
    response = _upload("note.pdf", payload, "application/pdf")
    assert response.status_code == 201
    assert response.json()["mime_type"] == "application/pdf"


def test_upload_accepts_docx_with_zip_signature():
    payload = b"PK\x03\x04" + b"fake zip body"
    response = _upload("note.docx", payload)
    assert response.status_code == 201


def test_upload_rejects_unsupported_extension_with_415():
    response = _upload("malware.exe", b"PE binary")
    assert response.status_code == 415
    detail = response.json()["detail"]
    assert detail["error"] == "unsupported_file_type"
    assert detail["extension"] == ".exe"
    assert ".pdf" in detail["allowed"]


def test_upload_rejects_pdf_without_signature_with_415():
    response = _upload("fake.pdf", b"not actually a pdf payload", "application/pdf")
    assert response.status_code == 415
    detail = response.json()["detail"]
    assert detail["error"] == "invalid_content"


def test_upload_rejects_docx_without_zip_signature_with_415():
    response = _upload("fake.docx", b"not a real docx body")
    assert response.status_code == 415
    detail = response.json()["detail"]
    assert detail["error"] == "invalid_content"


def test_upload_rejects_text_with_null_byte_with_415():
    response = _upload("binary.txt", b"hello\x00world", "text/plain")
    assert response.status_code == 415
    detail = response.json()["detail"]
    assert detail["error"] == "invalid_content"


def test_upload_rejects_empty_file_with_400():
    response = _upload("empty.txt", b"", "text/plain")
    assert response.status_code == 400


def test_upload_rejects_oversized_file_with_413(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 64)
    response = _upload("big.txt", b"X" * 128, "text/plain")
    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail["error"] == "file_too_large"
    assert detail["limit_bytes"] == 64
    assert detail["size_bytes"] == 128


def test_duplicate_upload_returns_409_referencing_existing_id():
    payload = b"this is a synthetic test document"
    first = _upload("a.txt", payload, "text/plain")
    assert first.status_code == 201
    existing_id = first.json()["id"]

    duplicate = _upload("renamed.txt", payload, "text/plain")
    assert duplicate.status_code == 409
    detail = duplicate.json()["detail"]
    assert detail["error"] == "duplicate"
    assert detail["existing_id"] == existing_id


def test_integrity_error_at_commit_returns_duplicate_referencing_winner(monkeypatch):
    payload = b"race-path synthetic content"
    content_hash = storage.compute_hash(payload)

    seed = session_module.SessionLocal()
    winner = Document(
        original_filename="winner.txt",
        stored_filename=f"{content_hash}.txt",
        mime_type="text/plain",
        size_bytes=len(payload),
        content_hash=content_hash,
        status="uploaded",
    )
    seed.add(winner)
    seed.commit()
    winner_id = winner.id
    seed.close()

    # Bypass the pre-check exactly once so commit fires the unique-constraint path.
    original_one_or_none = Query.one_or_none
    state = {"calls": 0}

    def patched_one_or_none(self):
        state["calls"] += 1
        if state["calls"] == 1:
            return None
        return original_one_or_none(self)

    monkeypatch.setattr(Query, "one_or_none", patched_one_or_none)

    session = session_module.SessionLocal()
    try:
        with pytest.raises(ingestion.DuplicateDocument) as exc_info:
            ingestion.ingest(session, "loser.txt", payload)
        assert exc_info.value.existing.id == winner_id
    finally:
        session.close()


def test_db_failure_after_file_write_cleans_up_orphan(monkeypatch):
    payload = b"clean-up-on-failure synthetic content"
    content_hash = storage.compute_hash(payload)
    expected_path = settings.upload_dir / f"{content_hash}.txt"

    session = session_module.SessionLocal()

    def boom():
        raise OperationalError("stmt", {}, Exception("db gone"))

    monkeypatch.setattr(session, "commit", boom)

    with pytest.raises(OperationalError):
        ingestion.ingest(session, "orphan.txt", payload)

    assert not expected_path.exists(), "file should be cleaned up after non-integrity DB failure"
    session.close()


def test_list_and_get_after_upload():
    response = _upload("note.md", b"# hello", "text/markdown")
    assert response.status_code == 201
    doc_id = response.json()["id"]

    listing = client.get("/documents/")
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["id"] == doc_id

    one = client.get(f"/documents/{doc_id}")
    assert one.status_code == 200
    assert one.json()["mime_type"] == "text/markdown"


def test_get_missing_document_returns_404():
    response = client.get("/documents/9999")
    assert response.status_code == 404

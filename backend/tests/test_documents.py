import io

from fastapi.testclient import TestClient

from app.main import app

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


def test_upload_rejects_unsupported_extension_with_415():
    response = _upload("malware.exe", b"PE binary")
    assert response.status_code == 415
    detail = response.json()["detail"]
    assert detail["error"] == "unsupported_file_type"
    assert detail["extension"] == ".exe"
    assert ".pdf" in detail["allowed"]


def test_upload_rejects_empty_file_with_400():
    response = _upload("empty.txt", b"", "text/plain")
    assert response.status_code == 400


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

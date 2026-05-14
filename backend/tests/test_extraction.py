import io

import docx
import fitz
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import parsing

client = TestClient(app)


def _upload_text(filename: str, content: str, content_type: str = "text/plain") -> int:
    files = {"file": (filename, io.BytesIO(content.encode("utf-8")), content_type)}
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    buf = io.BytesIO()
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(buf)
    return buf.getvalue()


def _build_pdf_bytes(page_texts: list[str | None]) -> bytes:
    pdf = fitz.open()
    for body in page_texts:
        page = pdf.new_page()
        if body:
            page.insert_text((72, 72), body)
    data = pdf.tobytes()
    pdf.close()
    return data


def _upload_bytes(filename: str, payload: bytes, content_type: str) -> int:
    files = {"file": (filename, io.BytesIO(payload), content_type)}
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def test_extract_txt_persists_one_page_with_source_text():
    doc_id = _upload_text("note.txt", "hello synthetic world\nline two")
    response = client.post(f"/documents/{doc_id}/extract")
    assert response.status_code == 200
    body = response.json()
    assert body["page_count"] == 1
    assert body["sources"] == {"text": 1}
    assert body["status"] == "extracted"

    pages = client.get(f"/documents/{doc_id}/pages").json()
    assert len(pages) == 1
    assert pages[0]["page_number"] == 1
    assert pages[0]["source"] == "text"
    assert "hello synthetic world" in pages[0]["text"]


def test_extract_md_persists_one_page_with_source_text():
    doc_id = _upload_text("readme.md", "# Title\n\ncontent body", "text/markdown")
    response = client.post(f"/documents/{doc_id}/extract")
    assert response.status_code == 200
    pages = client.get(f"/documents/{doc_id}/pages").json()
    assert pages[0]["source"] == "text"
    assert "# Title" in pages[0]["text"]


def test_extract_docx_persists_one_page_with_paragraph_text():
    payload = _build_docx_bytes(["First paragraph.", "Second paragraph."])
    doc_id = _upload_bytes(
        "test.docx",
        payload,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response = client.post(f"/documents/{doc_id}/extract")
    assert response.status_code == 200
    body = response.json()
    assert body["page_count"] == 1
    assert body["sources"] == {"docx": 1}

    pages = client.get(f"/documents/{doc_id}/pages").json()
    assert "First paragraph." in pages[0]["text"]
    assert "Second paragraph." in pages[0]["text"]


def test_extract_pdf_with_native_text_uses_native_source():
    payload = _build_pdf_bytes(["Hello synthetic PDF content."])
    doc_id = _upload_bytes("note.pdf", payload, "application/pdf")
    response = client.post(f"/documents/{doc_id}/extract")
    assert response.status_code == 200
    body = response.json()
    assert body["page_count"] == 1
    assert body["sources"] == {"native_pdf": 1}

    pages = client.get(f"/documents/{doc_id}/pages").json()
    assert "Hello synthetic PDF content" in pages[0]["text"]


def test_extract_multipage_pdf_preserves_page_ordering():
    payload = _build_pdf_bytes(["page one body", "page two body", "page three body"])
    doc_id = _upload_bytes("multi.pdf", payload, "application/pdf")
    response = client.post(f"/documents/{doc_id}/extract")
    assert response.status_code == 200
    assert response.json()["page_count"] == 3

    pages = client.get(f"/documents/{doc_id}/pages").json()
    assert [p["page_number"] for p in pages] == [1, 2, 3]
    assert "page one" in pages[0]["text"]
    assert "page two" in pages[1]["text"]
    assert "page three" in pages[2]["text"]


def test_extract_pdf_falls_back_to_ocr_when_page_has_no_native_text(monkeypatch):
    payload = _build_pdf_bytes([None])  # blank page, no text
    doc_id = _upload_bytes("blank.pdf", payload, "application/pdf")

    monkeypatch.setattr(parsing, "_ocr_page", lambda page: "STUBBED-OCR-TEXT")

    response = client.post(f"/documents/{doc_id}/extract")
    assert response.status_code == 200
    body = response.json()
    assert body["page_count"] == 1
    assert body["sources"] == {"ocr_pdf": 1}

    pages = client.get(f"/documents/{doc_id}/pages").json()
    assert pages[0]["text"] == "STUBBED-OCR-TEXT"
    assert pages[0]["source"] == "ocr_pdf"


def test_extract_pdf_mixed_native_and_ocr_pages(monkeypatch):
    payload = _build_pdf_bytes(["native page text", None])
    doc_id = _upload_bytes("mixed.pdf", payload, "application/pdf")

    monkeypatch.setattr(parsing, "_ocr_page", lambda page: "OCR-FALLBACK")

    response = client.post(f"/documents/{doc_id}/extract")
    assert response.status_code == 200
    body = response.json()
    assert body["page_count"] == 2
    assert body["sources"] == {"native_pdf": 1, "ocr_pdf": 1}

    pages = client.get(f"/documents/{doc_id}/pages").json()
    assert pages[0]["source"] == "native_pdf"
    assert "native page text" in pages[0]["text"]
    assert pages[1]["source"] == "ocr_pdf"
    assert pages[1]["text"] == "OCR-FALLBACK"


def test_extract_returns_404_for_unknown_document():
    response = client.post("/documents/9999/extract")
    assert response.status_code == 404


def test_pages_returns_404_for_unknown_document():
    response = client.get("/documents/9999/pages")
    assert response.status_code == 404


def test_repeat_extraction_is_idempotent_and_replaces_existing_pages():
    doc_id = _upload_text("v1.txt", "first synthetic content")

    first = client.post(f"/documents/{doc_id}/extract")
    assert first.status_code == 200
    assert first.json()["page_count"] == 1

    second = client.post(f"/documents/{doc_id}/extract")
    assert second.status_code == 200
    assert second.json()["page_count"] == 1

    pages = client.get(f"/documents/{doc_id}/pages").json()
    assert len(pages) == 1


def test_extraction_failure_marks_document_as_extraction_failed(monkeypatch):
    doc_id = _upload_text("kaboom.txt", "synthetic content for failure path")

    def boom(_doc):
        raise RuntimeError("synthetic parsing error")

    monkeypatch.setattr(parsing, "extract", boom)

    response = client.post(f"/documents/{doc_id}/extract")
    assert response.status_code == 500
    assert response.json()["detail"]["error"] == "extraction_failed"

    document = client.get(f"/documents/{doc_id}").json()
    assert document["status"] == "extraction_failed"


def test_failed_re_extraction_preserves_prior_pages_and_marks_failed(monkeypatch):
    doc_id = _upload_text("v1.txt", "first synthetic content")

    first = client.post(f"/documents/{doc_id}/extract")
    assert first.status_code == 200
    pages_before = client.get(f"/documents/{doc_id}/pages").json()
    assert len(pages_before) == 1

    def boom(_doc):
        raise RuntimeError("synthetic re-extraction failure")

    monkeypatch.setattr(parsing, "extract", boom)

    second = client.post(f"/documents/{doc_id}/extract")
    assert second.status_code == 500

    document = client.get(f"/documents/{doc_id}").json()
    assert document["status"] == "extraction_failed"

    pages_after = client.get(f"/documents/{doc_id}/pages").json()
    assert pages_after == pages_before, "prior page rows must survive a failed re-extraction"


def test_successful_re_extraction_replaces_prior_pages_atomically():
    doc_id = _upload_text("v1.txt", "synthetic content for re-extract")

    first = client.post(f"/documents/{doc_id}/extract")
    assert first.status_code == 200
    page_ids_before = [p["page_number"] for p in client.get(f"/documents/{doc_id}/pages").json()]

    second = client.post(f"/documents/{doc_id}/extract")
    assert second.status_code == 200
    pages_after = client.get(f"/documents/{doc_id}/pages").json()
    assert [p["page_number"] for p in pages_after] == page_ids_before
    assert len(pages_after) == 1


def test_uploaded_document_status_is_uploaded_until_extraction():
    doc_id = _upload_text("pending.txt", "synthetic")
    document = client.get(f"/documents/{doc_id}").json()
    assert document["status"] == "uploaded"

    pages_before = client.get(f"/documents/{doc_id}/pages").json()
    assert pages_before == []

    response = client.post(f"/documents/{doc_id}/extract")
    assert response.status_code == 200

    document = client.get(f"/documents/{doc_id}").json()
    assert document["status"] == "extracted"

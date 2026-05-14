import io

import docx
import fitz
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import chunking

client = TestClient(app)


def _upload_text(filename: str, content: str, content_type: str = "text/plain") -> int:
    files = {"file": (filename, io.BytesIO(content.encode("utf-8")), content_type)}
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def _upload_bytes(filename: str, payload: bytes, content_type: str) -> int:
    files = {"file": (filename, io.BytesIO(payload), content_type)}
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def _build_pdf_bytes(page_texts: list[str]) -> bytes:
    pdf = fitz.open()
    for body in page_texts:
        page = pdf.new_page()
        if body:
            page.insert_text((72, 72), body)
    data = pdf.tobytes()
    pdf.close()
    return data


def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    buf = io.BytesIO()
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(buf)
    return buf.getvalue()


def _extract(doc_id: int) -> None:
    response = client.post(f"/documents/{doc_id}/extract")
    assert response.status_code == 200, response.json()


def test_chunk_text_short_input_returns_single_chunk():
    out = chunking.chunk_text("hello world", chunk_size=1000, chunk_overlap=150)
    assert out == [(0, len("hello world"), "hello world")]


def test_chunk_text_empty_input_returns_no_chunks():
    assert chunking.chunk_text("", chunk_size=1000, chunk_overlap=150) == []


def test_chunk_text_overlapping_windows_are_deterministic():
    text = "x" * 250
    out = chunking.chunk_text(text, chunk_size=100, chunk_overlap=20)
    spans = [(s, e) for (s, e, _) in out]
    assert spans == [(0, 100), (80, 180), (160, 250)]
    again = chunking.chunk_text(text, chunk_size=100, chunk_overlap=20)
    assert [(s, e) for (s, e, _) in again] == spans


def test_chunk_text_window_content_matches_span():
    text = "".join(chr(ord("a") + (i % 26)) for i in range(250))
    out = chunking.chunk_text(text, chunk_size=100, chunk_overlap=20)
    for start, end, body in out:
        assert body == text[start:end]


def test_chunk_text_at_exact_chunk_size_is_single_chunk():
    text = "y" * 100
    out = chunking.chunk_text(text, chunk_size=100, chunk_overlap=20)
    assert out == [(0, 100, text)]


def test_chunk_short_txt_persists_one_chunk_with_provenance():
    doc_id = _upload_text("note.txt", "synthetic short content for chunking")
    _extract(doc_id)
    response = client.post(f"/documents/{doc_id}/chunk")
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["chunk_count"] == 1
    assert body["page_count"] == 1
    assert body["status"] == "chunked"
    assert body["chunk_size"] == settings.chunk_size
    assert body["chunk_overlap"] == settings.chunk_overlap

    chunks = client.get(f"/documents/{doc_id}/chunks").json()
    assert len(chunks) == 1
    assert chunks[0]["page_number"] == 1
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["char_start"] == 0
    assert chunks[0]["text"] == "synthetic short content for chunking"


def test_chunk_long_single_page_produces_multiple_overlapping_chunks(monkeypatch):
    monkeypatch.setattr(settings, "chunk_size", 100)
    monkeypatch.setattr(settings, "chunk_overlap", 20)

    text = "".join(chr(ord("a") + (i % 26)) for i in range(250))
    doc_id = _upload_text("long.txt", text)
    _extract(doc_id)

    response = client.post(f"/documents/{doc_id}/chunk")
    assert response.status_code == 200
    assert response.json()["chunk_count"] == 3

    chunks = client.get(f"/documents/{doc_id}/chunks").json()
    assert [(c["chunk_index"], c["char_start"], c["char_end"]) for c in chunks] == [
        (0, 0, 100), (1, 80, 180), (2, 160, 250),
    ]
    for c in chunks:
        assert c["text"] == text[c["char_start"]:c["char_end"]]


def test_chunks_do_not_cross_page_boundaries(monkeypatch):
    monkeypatch.setattr(settings, "chunk_size", 80)
    monkeypatch.setattr(settings, "chunk_overlap", 10)

    page_one = "P1-" + ("x" * 200)
    page_two = "P2-" + ("y" * 50)
    payload = _build_pdf_bytes([page_one, page_two])
    doc_id = _upload_bytes("multi.pdf", payload, "application/pdf")
    _extract(doc_id)

    response = client.post(f"/documents/{doc_id}/chunk")
    assert response.status_code == 200

    chunks = client.get(f"/documents/{doc_id}/chunks").json()
    assert chunks, "expected at least one chunk per page"
    pages_in_chunks = {c["page_number"] for c in chunks}
    assert pages_in_chunks == {1, 2}

    # Each chunk's text must be a substring of exactly one page's extracted text.
    pages = {p["page_number"]: p["text"] for p in client.get(f"/documents/{doc_id}/pages").json()}
    for c in chunks:
        page_text = pages[c["page_number"]]
        assert c["text"] == page_text[c["char_start"]:c["char_end"]]


def test_chunk_ordering_is_stable_across_pages(monkeypatch):
    monkeypatch.setattr(settings, "chunk_size", 60)
    monkeypatch.setattr(settings, "chunk_overlap", 10)

    payload = _build_pdf_bytes(["page-one " * 30, "page-two " * 30, "page-three " * 30])
    doc_id = _upload_bytes("triple.pdf", payload, "application/pdf")
    _extract(doc_id)

    client.post(f"/documents/{doc_id}/chunk")
    chunks = client.get(f"/documents/{doc_id}/chunks").json()

    keys = [(c["page_number"], c["chunk_index"]) for c in chunks]
    assert keys == sorted(keys)
    by_page: dict[int, list[int]] = {}
    for page, idx in keys:
        by_page.setdefault(page, []).append(idx)
    for indexes in by_page.values():
        assert indexes == list(range(len(indexes)))


def test_chunking_rejects_unextracted_document_with_409():
    doc_id = _upload_text("pending.txt", "synthetic")
    response = client.post(f"/documents/{doc_id}/chunk")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "chunking_failed"


def test_chunking_404_for_unknown_document():
    assert client.post("/documents/9999/chunk").status_code == 404
    assert client.get("/documents/9999/chunks").status_code == 404


def test_repeat_chunking_is_idempotent_and_replaces_prior_chunks():
    doc_id = _upload_text("v1.txt", "synthetic content for re-chunking")
    _extract(doc_id)

    first = client.post(f"/documents/{doc_id}/chunk").json()
    chunks_first = client.get(f"/documents/{doc_id}/chunks").json()

    second = client.post(f"/documents/{doc_id}/chunk").json()
    chunks_second = client.get(f"/documents/{doc_id}/chunks").json()

    assert second["chunk_count"] == first["chunk_count"]
    assert chunks_second == chunks_first


def test_chunking_after_re_extraction_replaces_chunks(monkeypatch):
    monkeypatch.setattr(settings, "chunk_size", 50)
    monkeypatch.setattr(settings, "chunk_overlap", 10)

    doc_id = _upload_text("v1.txt", "synthetic body to be chunked then re-extracted")
    _extract(doc_id)
    client.post(f"/documents/{doc_id}/chunk")
    chunks_before = client.get(f"/documents/{doc_id}/chunks").json()
    assert chunks_before

    _extract(doc_id)
    client.post(f"/documents/{doc_id}/chunk")
    chunks_after = client.get(f"/documents/{doc_id}/chunks").json()
    assert chunks_after == chunks_before


def test_chunking_a_docx_uses_single_page_provenance():
    payload = _build_docx_bytes(["First synthetic paragraph.", "Second synthetic paragraph."])
    doc_id = _upload_bytes(
        "doc.docx",
        payload,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    _extract(doc_id)

    response = client.post(f"/documents/{doc_id}/chunk")
    assert response.status_code == 200
    chunks = client.get(f"/documents/{doc_id}/chunks").json()
    assert chunks
    assert {c["page_number"] for c in chunks} == {1}

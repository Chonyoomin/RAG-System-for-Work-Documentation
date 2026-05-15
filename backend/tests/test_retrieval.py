import io

from fastapi.testclient import TestClient

from app.db import session as session_module
from app.main import app
from app.models import Chunk
from app.models.embedding import EMBEDDING_DIM
from app.services import embedding

client = TestClient(app)


# Deterministic, content-aware stub embedder. Same text -> same vector; texts
# sharing characters get partial cosine similarity. Lets the SQLite fallback
# path actually exercise ranking instead of trivially-tied parallel vectors.
def _text_to_vector(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    v = [0.0] * dim
    for ch in text.lower():
        v[ord(ch) % dim] += 1.0
    return v


def _install_content_aware_embedder(monkeypatch):
    monkeypatch.setattr(
        embedding.embedder,
        "embed_texts",
        lambda texts: [_text_to_vector(t) for t in texts],
    )


def _upload_text(filename: str, content: str) -> int:
    files = {"file": (filename, io.BytesIO(content.encode("utf-8")), "text/plain")}
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def _upload_extract_chunk_index(monkeypatch, filename: str, content: str) -> int:
    _install_content_aware_embedder(monkeypatch)
    doc_id = _upload_text(filename, content)
    assert client.post(f"/documents/{doc_id}/extract").status_code == 200
    assert client.post(f"/documents/{doc_id}/chunk").status_code == 200
    assert client.post(f"/documents/{doc_id}/index").status_code == 200
    return doc_id


def test_retrieve_rejects_empty_query():
    response = client.post("/retrieve", json={"query": ""})
    assert response.status_code == 422  # FastAPI/Pydantic validation


def test_retrieve_rejects_whitespace_only_query(monkeypatch):
    _install_content_aware_embedder(monkeypatch)
    response = client.post("/retrieve", json={"query": "   "})
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "retrieval_failed"


def test_retrieve_fails_cleanly_when_no_indexed_chunks_exist(monkeypatch):
    _install_content_aware_embedder(monkeypatch)
    response = client.post("/retrieve", json={"query": "anything"})
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "retrieval_failed"
    assert "no indexed chunks" in detail["reason"]


def test_retrieve_returns_results_with_provenance_fields(monkeypatch):
    doc_id = _upload_extract_chunk_index(
        monkeypatch, "alpha.txt", "alpha beta gamma synthetic"
    )
    response = client.post("/retrieve", json={"query": "alpha"})
    assert response.status_code == 200
    body = response.json()
    assert body["embedding_model"] == embedding.EMBEDDING_MODEL
    assert body["embedding_dim"] == EMBEDDING_DIM
    assert body["top_k"] >= 1
    assert body["query"] == "alpha"
    assert body["results"]
    first = body["results"][0]
    expected_keys = {
        "document_id", "page_id", "page_number", "chunk_id", "chunk_index",
        "char_start", "char_end", "text", "score", "distance",
        "embedding_model", "original_filename",
    }
    assert set(first.keys()) == expected_keys
    assert first["document_id"] == doc_id
    assert first["original_filename"] == "alpha.txt"


def test_retrieve_results_correspond_to_real_persisted_chunks(monkeypatch):
    doc_id = _upload_extract_chunk_index(
        monkeypatch, "real.txt", "synthetic alpha beta gamma corpus"
    )
    body = client.post("/retrieve", json={"query": "alpha"}).json()

    session = session_module.SessionLocal()
    try:
        real_ids = {c.id for c in session.query(Chunk).filter_by(document_id=doc_id).all()}
        for hit in body["results"]:
            assert hit["chunk_id"] in real_ids
    finally:
        session.close()


def test_retrieve_top_k_limits_result_count(monkeypatch):
    _install_content_aware_embedder(monkeypatch)
    for i in range(4):
        doc_id = _upload_text(f"doc-{i}.txt", f"alpha-{i} beta-{i} gamma-{i} synthetic content")
        assert client.post(f"/documents/{doc_id}/extract").status_code == 200
        assert client.post(f"/documents/{doc_id}/chunk").status_code == 200
        assert client.post(f"/documents/{doc_id}/index").status_code == 200

    body = client.post("/retrieve", json={"query": "alpha", "top_k": 2}).json()
    assert body["top_k"] == 2
    assert len(body["results"]) == 2


def test_retrieve_default_top_k_when_omitted(monkeypatch):
    _install_content_aware_embedder(monkeypatch)
    for i in range(7):
        doc_id = _upload_text(f"d-{i}.txt", f"alpha-{i} beta-{i} synthetic")
        client.post(f"/documents/{doc_id}/extract")
        client.post(f"/documents/{doc_id}/chunk")
        client.post(f"/documents/{doc_id}/index")

    body = client.post("/retrieve", json={"query": "alpha"}).json()
    from app.services.retrieval import DEFAULT_TOP_K
    assert body["top_k"] == DEFAULT_TOP_K
    assert len(body["results"]) == DEFAULT_TOP_K


def test_retrieve_does_not_expose_raw_vectors(monkeypatch):
    _upload_extract_chunk_index(monkeypatch, "novec.txt", "alpha synthetic")
    body = client.post("/retrieve", json={"query": "alpha"}).json()
    assert "embedding" not in body
    for hit in body["results"]:
        assert "embedding" not in hit


def test_retrieve_orders_results_by_descending_score(monkeypatch):
    _install_content_aware_embedder(monkeypatch)
    for i, body in enumerate(["alpha synthetic", "beta synthetic", "gamma synthetic"]):
        doc_id = _upload_text(f"o-{i}.txt", body)
        client.post(f"/documents/{doc_id}/extract")
        client.post(f"/documents/{doc_id}/chunk")
        client.post(f"/documents/{doc_id}/index")

    body = client.post("/retrieve", json={"query": "alpha", "top_k": 5}).json()
    scores = [r["score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)
    distances = [r["distance"] for r in body["results"]]
    assert distances == sorted(distances)


def test_retrieve_top_match_has_expected_document(monkeypatch):
    _install_content_aware_embedder(monkeypatch)
    docs: dict[str, int] = {}
    for body in ["alpha alpha alpha synthetic", "beta beta beta synthetic", "gamma gamma gamma synthetic"]:
        slug = body.split()[0]
        doc_id = _upload_text(f"{slug}.txt", body)
        client.post(f"/documents/{doc_id}/extract")
        client.post(f"/documents/{doc_id}/chunk")
        client.post(f"/documents/{doc_id}/index")
        docs[slug] = doc_id

    top = client.post("/retrieve", json={"query": "alpha alpha alpha"}).json()["results"][0]
    assert top["document_id"] == docs["alpha"]
    assert "alpha" in top["text"]


def test_retrieve_top_k_out_of_range_rejected_by_validation(monkeypatch):
    _install_content_aware_embedder(monkeypatch)
    bad_low = client.post("/retrieve", json={"query": "x", "top_k": 0})
    bad_high = client.post("/retrieve", json={"query": "x", "top_k": 9999})
    assert bad_low.status_code == 422
    assert bad_high.status_code == 422

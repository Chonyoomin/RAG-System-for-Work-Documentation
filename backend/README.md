# Backend

FastAPI + SQLAlchemy + PostgreSQL/pgvector. Phase 1 covers backend bootstrap plus safe document ingestion through deterministic chunking. Phase 2 adds local embedding generation and per-(chunk, model) vector persistence using LangChain's HuggingFace embeddings wrapper around `BAAI/bge-small-en-v1.5`. Retrieval, ranking, citation formatting, no-answer policy, answer generation, and frontend work are still out of scope.

## Layout

```text
app/
  main.py                FastAPI entrypoint, root logging config
  api/health.py          /health (liveness) and /health/db (readiness)
  api/documents.py       /documents/upload, /documents/, /documents/{id}
  core/config.py         env-driven settings (pydantic-settings)
  db/base.py             SQLAlchemy DeclarativeBase
  db/session.py          engine + sessionmaker + get_session dependency
  db/init_db.py          applies Alembic migrations programmatically
  models/
    system_info.py       bootstrap marker table
    document.py          upload metadata table
    page.py              extracted-page provenance table
    chunk.py             chunk-level provenance table
    embedding.py         per-(chunk, model) embedding row (Phase 2 storage)
  db/types.py            EmbeddingVector: pgvector on Postgres, JSON on SQLite
  services/storage.py    extension whitelist, hash, file write
  services/ingestion.py  validate -> hash -> dedupe -> store -> persist
  services/parsing.py    PDF/DOCX/TXT/MD parsing + Tesseract OCR fallback
  services/extraction.py parse -> persist pages (atomic, non-destructive on failure)
  services/chunking.py   deterministic char-window chunking over persisted pages
  services/embedding.py  lazy LangChain HuggingFaceEmbeddings wrapper (local model)
  services/indexing.py   embed persisted chunks -> upsert chunk_embeddings rows
  ingestion/             later phase
  retrieval/             later phase
  services/              later phase
migrations/
  env.py                 Alembic environment
  versions/0001_initial.py       enable pgvector + create system_info
  versions/0002_add_documents.py create documents table
tests/
  conftest.py            SQLite + tmp upload-dir fixtures (autouse)
  test_health.py         /health liveness test
  test_health_db.py      /health/db readiness test (integration)
  test_models.py         model registration on Base.metadata
  test_documents.py      upload, invalid type, duplicate, list, get
alembic.ini
pytest.ini
requirements.txt
requirements-dev.txt
```

## Local setup

From the repo root:

```powershell
docker compose up -d
copy .env.example .env
```

From `backend/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.db.init_db
uvicorn app.main:app --reload
```

`config.py` resolves `.env` to absolute paths. It reads the repo-root `.env` first and then `backend/.env` if present, so the documented setup works no matter which directory you launch commands from.

## Health endpoints

```powershell
curl http://localhost:8000/health
curl http://localhost:8000/health/db
```

- `GET /health` is liveness only. It returns `200 {"status":"ok","app":"...","version":"..."}` as long as the app process is running.
- `GET /health/db` is readiness. It returns `200 {"status":"ok","db":"ok"}` when Postgres is reachable, or `503 {"status":"down","db":"down","error":"..."}` when it is not.
- Database connection attempts are bounded by the 2-second `connect_timeout` configured in `db/session.py`.

## Document upload

`POST /documents/upload` accepts one `multipart/form-data` field named `file`. Allowed extensions are `.pdf`, `.docx`, `.txt`, and `.md`.

Upload flow:

1. Validate the filename extension against the allow-list. Unsupported types return `415` (`error: "unsupported_file_type"`).
2. Enforce `MAX_UPLOAD_BYTES` (`413`, default 25 MiB) in two layers. The early `Content-Length` check only fires when the declared size exceeds `limit + 1 MiB` — a generous slack so multipart envelope overhead never false-rejects a file at the actual limit. The precise enforcement is the chunked streaming read: a running total aborts the moment file bytes (not envelope) cross the limit.
3. Stream the body in 64 KiB chunks straight into a temporary file (`<upload_dir>/.incoming-<uuid>`) while updating SHA-256, checking the first chunk's magic bytes (`%PDF-` for PDFs, `PK\x03\x04` for DOCX), and incrementally UTF-8-decoding `.txt` / `.md` to reject NUL bytes or invalid encoding. The handler never holds a second full copy of the body in memory.
4. Empty bodies return `400`. For `.docx`, after streaming, run a deep structural check via the stdlib `zipfile` module: the archive must contain `[Content_Types].xml` and `word/document.xml`, otherwise `415 invalid_content` — so a generic ZIP renamed to `.docx` is rejected.
5. Look up the SHA-256 in the `documents` table. If found, return `409` referencing the existing row (the temporary file is removed by the handler's `finally`).
6. Promote the temporary file to `<upload_dir>/<sha256><ext>` via atomic rename, then insert a `documents` row and commit. On `IntegrityError` (concurrent insert won the race), return `409` referencing the winner; if the winner stored under a different extension, the loser's promoted file is deleted. On any other commit failure, the promoted file is removed before the error propagates.

Supporting endpoints:

- `GET /documents/` lists uploaded document metadata.
- `GET /documents/{id}` returns one document row or `404`.
- `POST /documents/{id}/extract` runs parsing + OCR fallback (see below) and persists pages.
- `GET /documents/{id}/pages` returns the persisted pages in order.
- `POST /documents/{id}/chunk` runs deterministic chunking over the persisted pages (see below) and persists chunks.
- `GET /documents/{id}/chunks` returns the persisted chunks in `(page_number, chunk_index)` order.
- `POST /documents/{id}/index` embeds the persisted chunks with the local model and writes one `chunk_embeddings` row per chunk for that model (see Indexing).
- `GET /documents/{id}/embeddings` returns provenance-only rows (`chunk_id`, `page_number`, `chunk_index`, `embedding_model`, `embedding_dim`) — vectors themselves are not exposed.

## Extraction

Extraction is decoupled from upload. Call `POST /documents/{id}/extract` to parse the stored file and persist page-level rows in the `pages` table.

Per-type behavior:

- **PDF** — `pymupdf` extracts page text in document order. Pages whose native text is empty (image-only / scanned) trigger an OCR fallback: the page is rendered at 200 DPI and run through local Tesseract via `pytesseract`. Source on each page is `native_pdf` or `ocr_pdf`.
- **DOCX** — `python-docx` reads paragraphs in order and joins them with blank lines into a single page (`page_number=1`, `source="docx"`). Phase 1 keeps DOCX as one provenance unit; later chunking can subdivide.
- **TXT / MD** — read directly as UTF-8 into a single page (`page_number=1`, `source="text"`).

Re-running `/extract` is **non-destructive on failure**: parsing runs first, and only after it succeeds are the existing `pages` rows replaced with the new ones in a single commit. If parsing or OCR throws, prior page rows are left intact and the document `status` is set to `extraction_failed` so the failure is visible without losing the last known-good extraction. Status transitions: `uploaded` → `extracted` on success; either `uploaded` or `extracted` → `extraction_failed` on a failed attempt; the next successful run flips back to `extracted`. The handler returns `500 {"error":"extraction_failed","reason":"..."}` for failures and `404` if the document doesn't exist. Tesseract must be installed locally for the OCR fallback path.

The `pages` table preserves the provenance keys later phases need: `document_id` foreign key, 1-based `page_number`, deterministic ordering by ordinal, and the `source` indicator. The chunking step references these rows.

## Chunking

Chunking is decoupled from extraction. Call `POST /documents/{id}/chunk` to split persisted page text into deterministic, fixed-size character windows and persist `chunks` rows.

Behavior:

- **Input is page rows, not raw uploads.** Chunking reads the `pages` table, so re-running it is a pure DB operation: no re-parsing, no re-OCR.
- **Per-page, no cross-page boundaries.** Each page is windowed independently. Chunks never span pages, which keeps citation and quote anchoring honest.
- **Fixed character windows with fixed overlap.** Defaults: `CHUNK_SIZE = 1000`, `CHUNK_OVERLAP = 150` (overrideable via env). The window step is `chunk_size - chunk_overlap`. A page whose text fits in one window produces a single chunk spanning `(0, len(text))`. Otherwise, windows advance by step until the final window reaches end-of-text. The overlap is constant; window text is exactly `page_text[char_start:char_end]`.
- **Provenance triple persisted per chunk.** Each chunk row carries `(document_id, page_id, page_number, chunk_index, char_start, char_end, text)`. `chunk_index` is 0-based per page. `(page_id, chunk_index)` is unique. The triple `(document_id, page_number, chunk_index)` plus the `char_start/char_end` offsets is what later indexing, retrieval, and exact-quote rendering will hang off of.
- **Requires extraction first.** If the document hasn't been extracted (or extraction left no pages), `/chunk` returns `409 {"error":"chunking_failed","reason":"..."}`. Unknown documents return `404`.
- **Idempotent replace on re-run.** Re-running `/chunk` deletes the document's existing chunk rows and writes a fresh deterministic set in a single commit. Same input → same output. After a successful re-extraction, the next `/chunk` call rebuilds chunks against the new pages.
- **Status transition.** A successful chunking call sets `document.status = "chunked"`. Re-running on an already-`chunked` document is allowed and remains idempotent.

## Storage location

Files are written to `<repo_root>/data/uploads/` by default. Override with `UPLOAD_DIR`. The size cap is `MAX_UPLOAD_BYTES` (default 26214400 = 25 MiB).

`data/uploads/` is already excluded by `.gitignore` along with other private-document and derived-artifact directories. Uploaded files should be treated as local-only working data and must not be committed.

## Tests

```powershell
pip install -r requirements-dev.txt
pytest
pytest -m integration
```

- Default `pytest` excludes integration tests via `pytest.ini`, so the fast suite does not need Postgres.
- `test_health_db.py` is marked `integration` and explicitly exercises `/health/db` against a live database.
- `tests/conftest.py` patches the upload directory to `tmp_path/uploads` and swaps the SQLAlchemy engine/session to a fresh SQLite database for non-integration tests.

## Migrations

Schema changes are migration-driven.

```powershell
python -m app.db.init_db                   # applies alembic upgrade head
alembic upgrade head
alembic revision -m "describe change"
alembic revision --autogenerate -m "..."
alembic downgrade -1
```

- `0001_initial` enables the `pgvector` extension and creates `system_info`.
- `0002_add_documents` creates the `documents` table used by the upload flow.
- `0003_add_pages` creates the `pages` table used by the extraction flow (FK to `documents` with `ON DELETE CASCADE`, unique on `(document_id, page_number)`).
- `0004_add_chunks` creates the `chunks` table used by the chunking flow (FKs to `documents` and `pages` with `ON DELETE CASCADE`, unique on `(page_id, chunk_index)`).
- `0005_add_chunk_embeddings` creates the `chunk_embeddings` table used by Phase 2 indexing (FKs to `documents`, `pages`, `chunks` with `ON DELETE CASCADE`, unique on `(chunk_id, embedding_model)`, `embedding` column typed as pgvector `Vector(384)`). The dim `384` is hardcoded in this migration so the historical schema step is deterministic and never depends on runtime config.

## Indexing

Indexing is decoupled from chunking. Call `POST /documents/{id}/index` to generate embeddings for the document's persisted chunks and write them to `chunk_embeddings`.

Behavior:

- **Input is chunk rows, not raw uploads or pages.** The flow loads `chunks` for the document and embeds `chunk.text` directly. No re-parsing, no re-OCR, no re-chunking.
- **Local embedding model only.** [app/services/embedding.py](app/services/embedding.py) wraps LangChain's `HuggingFaceEmbeddings` around `BAAI/bge-small-en-v1.5` (384-dim). The model loads lazily on first call so the fast test suite (which monkeypatches `embedder.embed_texts`) never pays the download cost. Running the real path the first time downloads the model into the local HuggingFace cache.
- **Per-(chunk, model) persistence.** One `chunk_embeddings` row per chunk per `embedding_model`, keyed by the existing `(chunk_id, embedding_model)` unique constraint. Each row carries the full provenance set: `document_id`, `page_id`, `chunk_id`, `page_number`, `chunk_index`, `embedding_model`, `embedding_dim`, `embedding`.
- **Deterministic re-index, scoped to the active model.** Re-running `/index` deletes only this `(document_id, embedding_model)` pair's existing rows and re-inserts in a single commit. Rows under a different `embedding_model` for the same chunks are left untouched. Same chunks + same model → same row count, no duplicates.
- **Requires chunking first.** If the document hasn't been chunked, `/index` returns `409 {"error":"indexing_failed","reason":"..."}`. Unknown documents return `404`. If the embedder ever returns the wrong vector count or wrong dim for the schema, `/index` aborts before writing anything.
- **Status transition.** A successful indexing call sets `document.status = "indexed"`. Re-running on an already-`indexed` document is allowed and remains deterministic. Status flow so far: `uploaded` → `extracted` → `chunked` → `indexed`.

Retrieval, similarity search, ranking, citations, and answer generation are not part of this slice and remain Phase 3+.

### Embedding dimension

The pgvector column dim is **schema, not runtime config**. Both migration `0005` and `app/models/embedding.py` pin it to `384` (the dim of the project's default local model, `BAAI/bge-small-en-v1.5`). Switching to a different embedding model with a different dim is **not** a config change — it requires:

1. A new migration that alters the `chunk_embeddings.embedding` column type to the new `Vector(N)`.
2. Bumping `EMBEDDING_DIM` in `app/models/embedding.py` in lockstep.
3. Coordinated re-embedding of every existing chunk under the new model name (existing rows under the old `embedding_model` are not silently compatible).

The `(chunk_id, embedding_model)` unique constraint exists so per-model upserts are clean, not so that mixed-dim rows can coexist in one column.

`system_info` remains as the lightweight bootstrap marker. `documents`, `pages`, and `chunks` are the operational tables backing upload, extraction, and chunking. `chunk_embeddings` is the Phase 2 storage foundation — embedding generation itself is not yet implemented.

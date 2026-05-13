# Backend

FastAPI + SQLAlchemy + PostgreSQL/pgvector. Phase 2 covers backend bootstrap plus safe document ingestion: health endpoints, database foundation, upload, hash-based deduplication, local file storage, and metadata tracking. OCR, text extraction, chunking, embeddings, retrieval, and answer generation are still out of scope.

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
    system_info.py       Phase 1 bootstrap marker table
    document.py          Phase 2 upload metadata table
  services/storage.py    extension whitelist, hash, file write
  services/ingestion.py  validate -> hash -> dedupe -> store -> persist
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

## Extraction

Extraction is decoupled from upload. Call `POST /documents/{id}/extract` to parse the stored file and persist page-level rows in the `pages` table.

Per-type behavior:

- **PDF** — `pymupdf` extracts page text in document order. Pages whose native text is empty (image-only / scanned) trigger an OCR fallback: the page is rendered at 200 DPI and run through local Tesseract via `pytesseract`. Source on each page is `native_pdf` or `ocr_pdf`.
- **DOCX** — `python-docx` reads paragraphs in order and joins them with blank lines into a single page (`page_number=1`, `source="docx"`). Phase 1 keeps DOCX as one provenance unit; later chunking can subdivide.
- **TXT / MD** — read directly as UTF-8 into a single page (`page_number=1`, `source="text"`).

Re-running `/extract` is **non-destructive on failure**: parsing runs first, and only after it succeeds are the existing `pages` rows replaced with the new ones in a single commit. If parsing or OCR throws, prior page rows are left intact and the document `status` is set to `extraction_failed` so the failure is visible without losing the last known-good extraction. Status transitions: `uploaded` → `extracted` on success; either `uploaded` or `extracted` → `extraction_failed` on a failed attempt; the next successful run flips back to `extracted`. The handler returns `500 {"error":"extraction_failed","reason":"..."}` for failures and `404` if the document doesn't exist. Tesseract must be installed locally for the OCR fallback path.

The `pages` table preserves the provenance keys later phases need: `document_id` foreign key, 1-based `page_number`, deterministic ordering by ordinal, and the `source` indicator. Chunking (next Phase 1 slice) will reference these rows.

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

`system_info` remains as the lightweight bootstrap marker. `documents` and `pages` are the operational tables backing upload and extraction respectively. Later Phase 1 work (chunking) and Phase 2 (indexing) will add `chunks` and embedding tables on top of this migration history.

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

1. Reject empty bodies (`400`) and oversized payloads above `MAX_UPLOAD_BYTES` (`413`, default 25 MiB).
2. Validate the filename extension against the allow-list. Unsupported types return `415` (`error: "unsupported_file_type"`).
3. Validate the bytes against a lightweight per-type signature check — `%PDF-` for PDFs, `PK\x03\x04` ZIP magic for DOCX, UTF-8 decodability with no NUL bytes for `.txt` / `.md`. Mismatches return `415` (`error: "invalid_content"`) so an `.exe` renamed to `.pdf` is rejected.
4. Compute a SHA-256 content hash and check the `documents` table for an existing row. If found, return `409` with the existing `id` and `content_hash` (no file write).
5. Write the file to `<upload_dir>/<sha256><ext>` (idempotent — concurrent same-content writes hit the same path with the same bytes).
6. Insert a `documents` row and commit. If the unique-hash constraint fires (concurrent insert won the race), return `409` referencing the winner. If commit fails for any other reason, the just-written file is removed before the error propagates so no orphans accumulate.

Supporting endpoints:

- `GET /documents/` lists uploaded document metadata.
- `GET /documents/{id}` returns one document row or `404`.

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
- `0002_add_documents` creates the `documents` table used by the Phase 2 ingestion flow.

`system_info` remains as the lightweight Phase 1 bootstrap marker. `documents` is the first Phase 2 operational table. Later phases can add `pages`, `chunks`, and processing-state tables on top of this migration history.

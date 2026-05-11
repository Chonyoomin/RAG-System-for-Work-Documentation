# Backend

FastAPI + SQLAlchemy + PostgreSQL/pgvector. Phase 2 — health endpoint, database foundation, and document ingestion (upload, hash-based dedup, local storage, metadata tracking). No OCR, text extraction, chunking, embeddings, retrieval, or generation logic yet.

## Layout

```
app/
  main.py                FastAPI entrypoint, root logging config
  api/health.py          /health (liveness + DB ping)
  api/documents.py       /documents/upload, /documents/, /documents/{id}
  core/config.py         env-driven settings (pydantic-settings)
  db/base.py             SQLAlchemy DeclarativeBase
  db/session.py          engine + sessionmaker + get_session dependency
  db/init_db.py          enables pgvector + Base.metadata.create_all
  models/document.py     Document model (id, hash, status, metadata)
  services/storage.py    extension whitelist, hash, file write
  services/ingestion.py  validate -> hash -> dedup -> store -> persist
  retrieval/             (later phase)
tests/
  conftest.py            SQLite + tmp upload-dir fixtures (autouse)
  test_health.py         /health smoke test
  test_documents.py      upload, invalid type, duplicate, list, get
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

Smoke test:

```powershell
curl http://localhost:8000/health
curl -F "file=@./sample.txt" http://localhost:8000/documents/upload
curl http://localhost:8000/documents/
```

Expected `/health`: `{"status":"ok","app":"Documentation RAG","version":"0.1.0","db":"ok"}`. If Postgres is unreachable, `db` flips to `down` while `status` stays `ok`.

## Document upload (Phase 2)

`POST /documents/upload` accepts a single `multipart/form-data` `file` field. Allowed extensions: `.pdf`, `.docx`, `.txt`, `.md`. The handler:

1. Validates the extension (rejects with `415` otherwise).
2. Reads the bytes and computes a SHA-256 content hash.
3. Looks up the hash in the `documents` table; if it exists, returns `409` with the existing `id` and `content_hash`.
4. Writes the bytes to `<upload_dir>/<sha256><ext>` (idempotent — collision is impossible by construction).
5. Inserts a `documents` row with `original_filename`, `stored_filename`, `mime_type`, `size_bytes`, `content_hash`, `status="uploaded"`, `uploaded_at`.

`status` is currently always `"uploaded"`. Phase 3 will advance it through `processing` / `processed` / `failed` as text extraction and indexing happen.

`GET /documents/` lists all documents; `GET /documents/{id}` returns one or `404`.

## Storage location

Files are written to `<repo_root>/data/uploads/` by default (overridable via the `UPLOAD_DIR` env var). The path is resolved from `config.py` so it stays stable regardless of which directory you run uvicorn from.

`data/uploads/` is excluded by `.gitignore` along with all other potential private-document directories — uploaded files never enter version control. Treat anything in this directory as private and ephemeral.

## Tests

```powershell
pip install -r requirements-dev.txt
pytest
```

`tests/conftest.py` is autouse and per-test:

- Points `settings.upload_dir` at a fresh `tmp_path / "uploads"`.
- Swaps `db.session.engine` / `db.session.SessionLocal` and `api.health.engine` for a fresh on-disk SQLite DB created from `Base.metadata`.

This means the suite runs with no Postgres, no shared disk state, and no test-to-test bleed. The Document model uses no pgvector columns yet, so SQLite is a faithful stand-in for Phase 2 schema.

## Migrations

`python -m app.db.init_db` is idempotent: it ensures the `vector` extension exists, then runs `Base.metadata.create_all()` for every model registered on `app.models`. As of Phase 2 that means the `documents` table. Re-run after pulling new model changes. When schema changes start needing version tracking, swap this for Alembic.

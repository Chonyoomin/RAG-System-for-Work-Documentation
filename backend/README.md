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
  main.py            FastAPI entrypoint
  api/health.py      /health (liveness) and /health/db (readiness)
  core/config.py     env-driven settings (pydantic-settings)
  db/base.py         SQLAlchemy DeclarativeBase
  db/session.py      engine + sessionmaker + get_session dependency
  models/
    system_info.py   bootstrap key/value table (Phase 1 marker; Phase 2 adds the real schema)
  ingestion/         (later phase)
  retrieval/         (later phase)
  services/          (later phase)
migrations/
  env.py             Alembic env (loads Base.metadata via app.models)
  versions/0001_initial.py  enable pgvector + create system_info
tests/
  conftest.py            SQLite + tmp upload-dir fixtures (autouse)
  test_health.py         /health smoke test
  test_documents.py      upload, invalid type, duplicate, list, get
  test_health.py     /health liveness test (no DB)
  test_health_db.py  /health/db readiness test (marked `integration`)
  test_models.py     model registration on Base.metadata (no DB)
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
alembic upgrade head
uvicorn app.main:app --reload
```

`config.py` resolves `.env` to absolute paths — it loads the repo-root `.env` first, then `backend/.env` if present (the latter wins). You can run any command from either directory and the same configuration applies.

Smoke test:

```powershell
curl http://localhost:8000/health
curl -F "file=@./sample.txt" http://localhost:8000/documents/upload
curl http://localhost:8000/documents/
curl http://localhost:8000/health        # liveness — does not touch the DB
curl http://localhost:8000/health/db     # readiness — pings Postgres (SELECT 1)
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
- `GET /health` always returns `200 {"status":"ok","app":"...","version":"..."}` as long as the app process is up.
- `GET /health/db` returns `200 {"status":"ok","db":"ok"}` when Postgres is reachable, or `503 {"status":"down","db":"down","error":"..."}` when it is not. The DB connection is bounded by a 2-second `connect_timeout` so the endpoint fails fast.

## Tests

```powershell
pip install -r requirements-dev.txt
pytest                       # fast suite — no DB required
pytest -m integration        # readiness check against a live Postgres
```

By default, `pytest.ini` excludes the `integration` marker so the suite runs quickly without infrastructure. The default test only hits `/health` (liveness, no DB). The integration test hits `/health/db` and requires Postgres reachable at `DATABASE_URL`.

## Migrations

`python -m app.db.init_db` is idempotent: it ensures the `vector` extension exists, then runs `Base.metadata.create_all()` for every model registered on `app.models`. As of Phase 2 that means the `documents` table. Re-run after pulling new model changes. When schema changes start needing version tracking, swap this for Alembic.
Alembic. Run from `backend/`:

```powershell
alembic upgrade head                       # apply all migrations
alembic revision -m "describe change"      # new empty migration
alembic revision --autogenerate -m "..."   # diff Base.metadata vs DB
alembic downgrade -1                       # roll back one
```

`migrations/env.py` reads `DATABASE_URL` from `app.core.config.settings` and imports `app.models` to populate `Base.metadata`. The initial migration enables the `pgvector` extension and creates the `system_info` table.

`system_info` is a small key/value table used as a bootstrap marker — it validates the DB layer end-to-end (model declared, migration applied, table reachable) without committing to the Phase 2 ingestion schema. Phase 2 will add `documents`, `pages`, and `chunks` alongside it.

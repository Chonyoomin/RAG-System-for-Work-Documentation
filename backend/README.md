# Backend

FastAPI + SQLAlchemy + PostgreSQL/pgvector. Phase 1 only — health endpoint and database foundation. No ingestion, indexing, retrieval, or generation logic yet.

## Layout

```
app/
  main.py            FastAPI entrypoint
  api/health.py      health endpoint with DB ping
  core/config.py     env-driven settings (pydantic-settings)
  db/base.py         SQLAlchemy DeclarativeBase
  db/session.py      engine + sessionmaker + get_session dependency
  db/init_db.py      creates pgvector extension + Base.metadata.create_all
  ingestion/         (later phase)
  retrieval/         (later phase)
  services/          (later phase)
  models/            (later phase)
tests/
  test_health.py     /health smoke test
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
```

Expected: `{"status":"ok","app":"Documentation RAG","version":"0.1.0","db":"ok"}`. If Postgres is unreachable, `db` flips to `down` while `status` stays `ok`.

## Tests

```powershell
pip install -r requirements-dev.txt
pytest
```

The health test uses FastAPI's `TestClient` and runs without a live database — the endpoint reports `db: down` if Postgres is missing, which the test allows.

## Migrations

Phase 1 uses `python -m app.db.init_db` (idempotent: enables `vector`, then creates whatever tables are declared on `Base.metadata`). When the schema starts changing across versions in Phase 2+, swap this for Alembic.

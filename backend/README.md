# Backend

FastAPI + SQLAlchemy + PostgreSQL/pgvector. Phase 1 only — health endpoint and database foundation. No ingestion, indexing, retrieval, or generation logic yet.

## Layout

```
app/
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
curl http://localhost:8000/health        # liveness — does not touch the DB
curl http://localhost:8000/health/db     # readiness — pings Postgres (SELECT 1)
```

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

Alembic. Run from `backend/`:

```powershell
alembic upgrade head                       # apply all migrations
alembic revision -m "describe change"      # new empty migration
alembic revision --autogenerate -m "..."   # diff Base.metadata vs DB
alembic downgrade -1                       # roll back one
```

`migrations/env.py` reads `DATABASE_URL` from `app.core.config.settings` and imports `app.models` to populate `Base.metadata`. The initial migration enables the `pgvector` extension and creates the `system_info` table.

`system_info` is a small key/value table used as a bootstrap marker — it validates the DB layer end-to-end (model declared, migration applied, table reachable) without committing to the Phase 2 ingestion schema. Phase 2 will add `documents`, `pages`, and `chunks` alongside it.

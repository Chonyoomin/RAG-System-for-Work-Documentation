import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  -- ensure models register on Base.metadata
from app.api import health as health_module
from app.core import config as config_module
from app.db import session as session_module
from app.db.base import Base


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(config_module.settings, "upload_dir", upload_dir)

    test_db = tmp_path / "test.db"
    test_engine = create_engine(f"sqlite:///{test_db}", future=True)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    monkeypatch.setattr(session_module, "engine", test_engine)
    monkeypatch.setattr(session_module, "SessionLocal", TestSession)
    monkeypatch.setattr(health_module, "engine", test_engine)
    yield

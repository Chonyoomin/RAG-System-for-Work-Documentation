import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.integration

client = TestClient(app)


def test_readiness_with_live_db():
    response = client.get("/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}

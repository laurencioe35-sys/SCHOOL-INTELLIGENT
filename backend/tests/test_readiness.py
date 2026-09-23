from fastapi.testclient import TestClient

from app.main import app
from app.migrations import SCHEMA_VERSION


def test_readiness_reports_database_and_schema_state():
    response = TestClient(app).get("/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["database_ok"] is True
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["required_schema_version"] == SCHEMA_VERSION
    assert payload["ready"] is True
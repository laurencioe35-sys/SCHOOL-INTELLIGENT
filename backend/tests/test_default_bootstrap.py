from fastapi.testclient import TestClient

from app.bootstrap import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, DEFAULT_TENANT_ID
from app.main import app


def test_default_admin_login_works():
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_id": str(DEFAULT_TENANT_ID),
            "email": DEFAULT_ADMIN_EMAIL,
            "password": DEFAULT_ADMIN_PASSWORD,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["role"] == "admin"
    assert payload["tenant_id"] == str(DEFAULT_TENANT_ID)

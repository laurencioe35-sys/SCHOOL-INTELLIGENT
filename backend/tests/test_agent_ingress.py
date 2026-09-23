from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.security import create_access_token


def test_transcript_ingress_publishes_tenant_scoped_event():
    tenant_id = uuid4()
    token = create_access_token(uuid4(), tenant_id, "teacher")

    with patch("app.routes._publish_transcript_event", return_value="1-0") as publish:
        response = TestClient(app).post(
            "/api/v1/agent/events/transcript",
            json={"session_id": "class-1", "raw_text": "Hoy estudiaremos fracciones", "priority": "high"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 202
    assert response.json()["stream_id"] == "1-0"
    event = publish.call_args.args[0]
    assert event["tenant_id"] == str(tenant_id)
    assert event["type"] == "transcript_chunk"


def test_transcript_ingress_rejects_unauthorized_role():
    token = create_access_token(uuid4(), uuid4(), "student")
    response = TestClient(app).post(
        "/api/v1/agent/events/transcript",
        json={"session_id": "class-1", "raw_text": "texto"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.security import create_access_token


def test_audio_ingress_publishes_tenant_scoped_event():
    token = create_access_token(uuid4(), uuid4(), "teacher")
    with patch("app.routes._publish_audio_event", return_value="1-0") as publish:
        response = TestClient(app).post(
            "/api/v1/agent/events/audio",
            files={"audio": ("class.wav", b"audio-bytes", "audio/wav")},
            data={"session_id": "class-1"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 202
    assert publish.call_args.args[0]["type"] == "audio_chunk"
    assert publish.call_args.args[0]["tenant_id"]
    assert publish.call_args.args[0]["dispatch_mode"] == "auto"


def test_audio_ingress_allows_manual_transcription_review():
    token = create_access_token(uuid4(), uuid4(), "teacher")
    with patch("app.routes._publish_audio_event", return_value="1-0") as publish:
        response = TestClient(app).post(
            "/api/v1/agent/events/audio",
            files={"audio": ("class.webm", b"audio-bytes", "audio/webm")},
            data={"session_id": "class-1", "dispatch_mode": "manual"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 202
    assert publish.call_args.args[0]["dispatch_mode"] == "manual"

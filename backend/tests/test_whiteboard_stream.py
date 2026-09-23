from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal, initialize_db
from app.main import app
from app.models import Tenant, User
from app.security import create_access_token


def test_whiteboard_websocket_streams_authenticated_operations():
    initialize_db()
    tenant_id = uuid4()
    user_id = uuid4()
    with SessionLocal() as db:
        db.add(Tenant(id=tenant_id, name=f"Realtime {tenant_id.hex[:8]}"))
        db.add(User(id=user_id, tenant_id=tenant_id, email=f"ws-{tenant_id.hex[:8]}@example.com", password_hash="hash", role="admin"))
        db.commit()

    token = create_access_token(user_id, tenant_id, "admin")
    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/whiteboard/ws-room/stream?token={token}") as websocket:
            snapshot = websocket.receive_json()
            assert snapshot["type"] == "snapshot"

            websocket.send_json({
                "operation_id": f"op-{uuid4().hex}",
                "operation_type": "stroke",
                "payload": {"points": [[1, 2], [3, 4]], "tool": "pen"},
            })
            operation = websocket.receive_json()
            assert operation["type"] == "operation"
            assert operation["actor_id"] == str(user_id)
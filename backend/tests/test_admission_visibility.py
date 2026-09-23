from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Tenant, User
from app.security import create_access_token


def test_student_cannot_list_admission_applications():
    client = TestClient(app)
    tenant_id, user_id = uuid4(), uuid4()
    with SessionLocal() as db:
        db.add_all([
            Tenant(id=tenant_id, name="Visibility school"),
            User(id=user_id, tenant_id=tenant_id, email="student-visible@example.com", password_hash="hash", role="student"),
        ])
        db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user_id, tenant_id, 'student')}"}

    response = client.get("/api/v1/admissions/applications", headers=headers)

    assert response.status_code == 403
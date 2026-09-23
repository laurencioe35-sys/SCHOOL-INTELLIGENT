from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Course, Enrollment, Grade, Student, Tenant, User
from app.security import create_access_token
from app.security import create_access_token, hash_password


def test_student_me_endpoints_are_identity_and_tenant_scoped():
    client = TestClient(app)
    tenant_id = uuid4()
    student_id = uuid4()
    user_id = uuid4()
    course_id = uuid4()
    with SessionLocal() as db:
        db.add_all([
            Tenant(id=tenant_id, name="Portal school"),
            Student(id=student_id, tenant_id=tenant_id, first_name="Ada", last_name="Luz", document_number="ME-1"),
            User(id=user_id, tenant_id=tenant_id, student_id=student_id, email="ada@example.com", password_hash=hash_password("secret"), role="student"),
            Course(id=course_id, tenant_id=tenant_id, code="MATH", name="Matematicas"),
            Enrollment(tenant_id=tenant_id, student_id=student_id, course_id=course_id),
            Grade(tenant_id=tenant_id, student_id=student_id, course_id=course_id, score=95),
        ])
        db.commit()

    headers = {"Authorization": f"Bearer {create_access_token(user_id, tenant_id, 'student')}"}
    grades = client.get("/api/v1/students/me/grades", headers=headers)
    courses = client.get("/api/v1/students/me/courses", headers=headers)

    assert grades.status_code == 200
    assert [grade["score"] for grade in grades.json()] == [95]
    assert courses.status_code == 200
    assert [course["code"] for course in courses.json()] == ["MATH"]

    login = client.post(
        "/api/v1/auth/login",
        json={"tenant_id": str(tenant_id), "email": "ada@example.com", "password": "secret"},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "student"


def test_unlinked_authenticated_user_cannot_access_student_me_data():
    client = TestClient(app)
    tenant_id = uuid4()
    user_id = uuid4()
    with SessionLocal() as db:
        db.add_all([
            Tenant(id=tenant_id, name="Unlinked school"),
            User(id=user_id, tenant_id=tenant_id, email="staff@example.com", password_hash="hash", role="staff"),
        ])
        db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user_id, tenant_id, 'staff')}"}

    response = client.get("/api/v1/students/me/grades", headers=headers)

    assert response.status_code == 404
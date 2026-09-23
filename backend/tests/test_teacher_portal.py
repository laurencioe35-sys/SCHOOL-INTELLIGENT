from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Course, Grade, TeacherCourse, Tenant, User
from app.security import create_access_token


def test_teacher_portal_only_reads_assigned_course_grades():
    client = TestClient(app)
    tenant_id, teacher_id, course_id = uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        db.add_all([
            Tenant(id=tenant_id, name="Teacher school"),
            User(id=teacher_id, tenant_id=tenant_id, email="teacher@example.com", password_hash="hash", role="teacher"),
            Course(id=course_id, tenant_id=tenant_id, code="HIST", name="Historia"),
            TeacherCourse(tenant_id=tenant_id, teacher_user_id=teacher_id, course_id=course_id),
            Grade(tenant_id=tenant_id, student_id=uuid4(), course_id=course_id, score=91),
        ])
        db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(teacher_id, tenant_id, 'teacher')}"}

    courses = client.get("/api/v1/teachers/me/courses", headers=headers)
    grades = client.get(f"/api/v1/teachers/me/courses/{course_id}/grades", headers=headers)
    unknown = client.get(f"/api/v1/teachers/me/courses/{uuid4()}/grades", headers=headers)

    assert courses.status_code == 200
    assert courses.json()[0]["code"] == "HIST"
    assert grades.status_code == 200
    assert grades.json()[0]["score"] == 91
    assert unknown.status_code == 404
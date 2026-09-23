from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Course, Grade, GuardianStudent, Student, Tenant, User
from app.security import create_access_token, hash_password


def test_guardian_portal_only_reads_linked_student_grades():
    client = TestClient(app)
    tenant_id, guardian_id, student_id = uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        db.add_all([
            Tenant(id=tenant_id, name="Guardian school"),
            User(id=guardian_id, tenant_id=tenant_id, email="guardian@example.com", password_hash=hash_password("secret"), role="guardian"),
            Student(id=student_id, tenant_id=tenant_id, first_name="Nina", last_name="Sol", document_number="G-1"),
            GuardianStudent(tenant_id=tenant_id, guardian_user_id=guardian_id, student_id=student_id),
            Course(id=uuid4(), tenant_id=tenant_id, code="SCI", name="Ciencias"),
        ])
        db.commit()
        course_id = db.query(Course).filter(Course.code == "SCI").one().id
        db.add(Grade(tenant_id=tenant_id, student_id=student_id, course_id=course_id, score=88))
        db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(guardian_id, tenant_id, 'guardian')}"}

    students = client.get("/api/v1/guardians/me/students", headers=headers)
    grades = client.get(f"/api/v1/guardians/me/students/{student_id}/grades", headers=headers)
    unknown = client.get(f"/api/v1/guardians/me/students/{uuid4()}/grades", headers=headers)

    assert students.status_code == 200
    assert students.json()[0]["id"] == str(student_id)
    assert grades.status_code == 200
    assert grades.json()[0]["score"] == 88
    assert unknown.status_code == 404
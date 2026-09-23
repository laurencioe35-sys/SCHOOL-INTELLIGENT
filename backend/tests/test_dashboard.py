from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Tenant, User
from app.security import create_access_token


def _auth_headers(tenant_id: str, role: str = "admin") -> dict[str, str]:
    token = create_access_token(user_id=uuid4(), tenant_id=uuid4(), role=role)
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_summary_includes_business_metrics():
    client = TestClient(app)
    tenant_id = str(uuid4())
    headers = {"Authorization": f"Bearer {create_access_token(user_id=uuid4(), tenant_id=tenant_id, role='admin')}"}

    student_resp = client.post(
        "/api/v1/students",
        json={"first_name": "Ana", "last_name": "Lopez", "document_number": "1001"},
        headers=headers,
    )
    assert student_resp.status_code == 201

    course_resp = client.post(
        "/api/v1/courses",
        json={"code": "MAT-101", "name": "Matemáticas I"},
        headers=headers,
    )
    assert course_resp.status_code == 201

    summary_resp = client.get("/api/v1/dashboard/summary", headers=headers)
    assert summary_resp.status_code == 200
    payload = summary_resp.json()
    assert payload["tenant_id"] == tenant_id
    assert payload["students"] >= 1
    assert payload["courses"] >= 1
    assert payload["health"] == "ok"


def test_student_enrollment_and_grade_flow():
    client = TestClient(app)
    tenant_id = str(uuid4())
    headers = {"Authorization": f"Bearer {create_access_token(user_id=uuid4(), tenant_id=tenant_id, role='admin')}"}

    student = client.post(
        "/api/v1/students",
        json={"first_name": "Luis", "last_name": "Pérez", "document_number": "1002"},
        headers=headers,
    )
    course = client.post(
        "/api/v1/courses",
        json={"code": "BIO-202", "name": "Biología"},
        headers=headers,
    )

    enroll = client.post(
        "/api/v1/enrollments",
        json={"student_id": student.json()["id"], "course_id": course.json()["id"]},
        headers=headers,
    )
    assert enroll.status_code == 201
    assert enroll.json()["student_id"] == student.json()["id"]

    grade = client.post(
        "/api/v1/grades",
        json={"student_id": student.json()["id"], "course_id": course.json()["id"], "score": 92, "comment": "Excelente avance"},
        headers=headers,
    )
    assert grade.status_code == 201
    assert grade.json()["score"] == 92

    summary = client.get("/api/v1/dashboard/summary", headers=headers)
    payload = summary.json()
    assert payload["students"] >= 1
    assert payload["courses"] >= 1
    assert payload["enrollments"] >= 1
    assert payload["average_grade"] >= 92


def test_executive_summary_reports_operational_kpis():
    client = TestClient(app)
    tenant_id = str(uuid4())
    headers = {"Authorization": f"Bearer {create_access_token(user_id=uuid4(), tenant_id=tenant_id, role='admin')}"}

    student = client.post(
        "/api/v1/students",
        json={"first_name": "María", "last_name": "Ruiz", "document_number": "1003"},
        headers=headers,
    )
    course = client.post(
        "/api/v1/courses",
        json={"code": "HIS-305", "name": "Historia"},
        headers=headers,
    )
    client.post(
        "/api/v1/enrollments",
        json={"student_id": student.json()["id"], "course_id": course.json()["id"]},
        headers=headers,
    )
    client.post(
        "/api/v1/grades",
        json={"student_id": student.json()["id"], "course_id": course.json()["id"], "score": 88, "comment": "Muy bien"},
        headers=headers,
    )
    client.post(
        "/api/v1/billing/invoices",
        json={
            "student_id": student.json()["id"],
            "concept": "Mensualidad",
            "amount_cents": 150000,
            "currency": "PEN",
            "due_date": "2026-09-30T00:00:00Z",
        },
        headers=headers,
    )

    response = client.get("/api/v1/reports/executive-summary", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == tenant_id
    assert payload["students"] >= 1
    assert payload["courses"] >= 1
    assert payload["average_grade"] >= 88
    assert payload["attendance_rate"] >= 0
    assert payload["outstanding_invoices_cents"] >= 150000


def test_staff_roster_and_workload_api_are_available_to_admins():
    client = TestClient(app)
    tenant_id = uuid4()
    headers = {"Authorization": f"Bearer {create_access_token(user_id=uuid4(), tenant_id=tenant_id, role='admin')}"}

    teacher_user_id = uuid4()
    with SessionLocal() as db:
        db.add_all([
            Tenant(id=tenant_id, name="Operaciones Escuela"),
            User(id=teacher_user_id, tenant_id=tenant_id, email="docente@escuela.com", password_hash="hash", role="teacher"),
            User(id=uuid4(), tenant_id=tenant_id, email="personal@escuela.com", password_hash="hash", role="staff"),
        ])
        db.commit()

    course_id = uuid4()
    with SessionLocal() as db:
        from app.models import Course, TeacherCourse
        db.add(Course(id=course_id, tenant_id=tenant_id, code="OPS-102", name="Operaciones", active=True))
        db.add(TeacherCourse(tenant_id=tenant_id, teacher_user_id=teacher_user_id, course_id=course_id, active=True))
        db.commit()

    roster = client.get("/api/v1/staff/roster", headers=headers)
    workload = client.get("/api/v1/staff/workload", headers=headers)

    assert roster.status_code == 200
    assert workload.status_code == 200
    assert len(roster.json()) >= 2
    assert any(item["role"] == "teacher" for item in roster.json())
    assert workload.json()[0]["teacher_user_id"] == str(teacher_user_id)

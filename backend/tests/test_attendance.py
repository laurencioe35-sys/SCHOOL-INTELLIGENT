from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.security import create_access_token


def test_student_attendance_flow_and_dashboard_rate():
    client = TestClient(app)
    tenant_id = str(uuid4())
    headers = {
        "Authorization": f"Bearer {create_access_token(user_id=uuid4(), tenant_id=tenant_id, role='teacher')}"
    }

    student = client.post(
        "/api/v1/students",
        json={"first_name": "Marta", "last_name": "Silva", "document_number": "2001"},
        headers=headers,
    )
    course = client.post(
        "/api/v1/courses",
        json={"code": "FIS-101", "name": "Física"},
        headers=headers,
    )

    enrollment = client.post(
        "/api/v1/enrollments",
        json={"student_id": student.json()["id"], "course_id": course.json()["id"]},
        headers=headers,
    )
    assert enrollment.status_code == 201

    attendance = client.post(
        "/api/v1/attendances",
        json={
            "student_id": student.json()["id"],
            "course_id": course.json()["id"],
            "session_date": "2026-09-14",
            "present": True,
        },
        headers=headers,
    )
    assert attendance.status_code == 201
    assert attendance.json()["present"] is True

    summary = client.get("/api/v1/dashboard/summary", headers=headers)
    payload = summary.json()
    assert payload["attendance_rate"] >= 0.9

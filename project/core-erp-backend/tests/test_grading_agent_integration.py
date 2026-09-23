"""
Tests de integración: ingesta de notas generadas por grading_agent
(ai-agents-engine) a través de /grades/submit-from-agent.

Corren contra la misma base Postgres/Redis reales que tests/test_erp.py
(ver ese archivo para el patrón general).
"""
import os

os.environ["ERP_DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/erp_educativo_test"
os.environ["ERP_REDIS_URL"] = "redis://localhost:6379/1"

import pytest
from fastapi.testclient import TestClient

from database.connection import engine
from database.models import Base, Grade, GradedBy
from database.connection import SessionLocal
from main import app
import api.grades as grades_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    # api/grades.py lee AI_AGENTS_INTERNAL_KEY una sola vez al importarse
    # (mismo patrón que ERP_SECRET_KEY en auth.py), y ya pudo haberse
    # importado antes con el valor vacío si otro archivo de test corrió
    # primero — por eso se fija en el MÓDULO ya importado, no solo en
    # os.environ (que ya no tendría efecto a esta altura).
    grades_module.AI_AGENTS_INTERNAL_KEY = "test-internal-key"
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    import redis
    r = redis.from_url(os.environ["ERP_REDIS_URL"])
    r.flushdb()
    yield


def register_teacher(organization_name="Colegio Test"):
    resp = client.post("/auth/register", json={
        "full_name": "Prof. Test", "email": "teacher@test.pe", "password": "clave123",
        "role": "teacher", "organization_name": organization_name,
    })
    assert resp.status_code == 200
    return resp.json()["access_token"]


def register_student(organization_name="Colegio Test"):
    resp = client.post("/auth/register", json={
        "full_name": "Alumno Test", "email": "student2@test.pe", "password": "clave123",
        "organization_name": organization_name,
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    import base64, json as jsonlib
    payload_b64 = token.split(".")[0]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = jsonlib.loads(base64.urlsafe_b64decode(payload_b64))
    return payload["sub"]


def _setup_classroom_with_enrolled_student():
    teacher_token = register_teacher()
    student_id = register_student()
    classroom_id = client.post(
        "/classrooms", json={"name": "Aula IA"}, headers={"Authorization": f"Bearer {teacher_token}"}
    ).json()["id"]
    resp = client.post(
        "/students/enroll",
        json={"student_id": student_id, "classroom_id": classroom_id},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 200
    return classroom_id, student_id


def test_submit_from_agent_without_internal_key_is_rejected():
    classroom_id, student_id = _setup_classroom_with_enrolled_student()
    resp = client.post(
        "/grades/submit-from-agent",
        json={
            "student_id": student_id, "classroom_id": classroom_id,
            "score_0_to_1": 0.9, "feedback": "Buena respuesta, cubrió los puntos clave.",
        },
    )
    assert resp.status_code == 401


def test_submit_from_agent_with_wrong_key_is_rejected():
    classroom_id, student_id = _setup_classroom_with_enrolled_student()
    resp = client.post(
        "/grades/submit-from-agent",
        json={
            "student_id": student_id, "classroom_id": classroom_id,
            "score_0_to_1": 0.9, "feedback": "x",
        },
        headers={"X-Internal-Service-Key": "clave-incorrecta"},
    )
    assert resp.status_code == 401


def test_submit_from_agent_rejects_unenrolled_student():
    teacher_token = register_teacher()
    student_id = register_student()
    classroom_id = client.post(
        "/classrooms", json={"name": "Aula IA"}, headers={"Authorization": f"Bearer {teacher_token}"}
    ).json()["id"]
    # NO se matricula al alumno.
    resp = client.post(
        "/grades/submit-from-agent",
        json={
            "student_id": student_id, "classroom_id": classroom_id,
            "score_0_to_1": 0.9, "feedback": "x",
        },
        headers={"X-Internal-Service-Key": "test-internal-key"},
    )
    assert resp.status_code == 400
    assert "matriculado" in resp.json()["detail"]


def test_submit_from_agent_scales_score_and_consolidates():
    """0.9 (escala 0-1 del grading_agent) debe consolidarse como 18.0
    (escala 0-20 usada por el resto del ERP), con graded_by/feedback
    correctamente propagados hasta la tabla final."""
    classroom_id, student_id = _setup_classroom_with_enrolled_student()

    resp = client.post(
        "/grades/submit-from-agent",
        json={
            "student_id": student_id,
            "classroom_id": classroom_id,
            "score_0_to_1": 0.9,
            "feedback": "Mencionó los 3 puntos clave esperados.",
            "needs_teacher_review": False,
            "session_id": "session-demo-001",
        },
        headers={"X-Internal-Service-Key": "test-internal-key"},
    )
    assert resp.status_code == 200
    assert resp.json()["queue_length"] == 1

    from workers.batch_db_worker import run_once
    count = run_once()
    assert count == 1

    db = SessionLocal()
    try:
        grade = db.query(Grade).filter(Grade.student_id == student_id).first()
        assert grade is not None
        assert grade.score == 18.0
        assert grade.graded_by == GradedBy.ai_grading_agent
        assert grade.feedback == "Mencionó los 3 puntos clave esperados."
        assert grade.needs_teacher_review is False
    finally:
        db.close()


def test_submit_from_agent_flags_needs_teacher_review():
    classroom_id, student_id = _setup_classroom_with_enrolled_student()

    resp = client.post(
        "/grades/submit-from-agent",
        json={
            "student_id": student_id,
            "classroom_id": classroom_id,
            "score_0_to_1": 0.4,
            "feedback": "Respuesta ambigua, requiere criterio del docente.",
            "needs_teacher_review": True,
        },
        headers={"X-Internal-Service-Key": "test-internal-key"},
    )
    assert resp.status_code == 200

    from workers.batch_db_worker import run_once
    run_once()

    db = SessionLocal()
    try:
        grade = db.query(Grade).filter(Grade.student_id == student_id).first()
        assert grade.needs_teacher_review is True
    finally:
        db.close()


def test_submit_from_agent_unknown_key_disabled_message(monkeypatch):
    """Si AI_AGENTS_INTERNAL_KEY no está configurada, el endpoint debe
    quedar deshabilitado (fail-closed) en vez de aceptar cualquier
    request sin autenticación."""
    import api.grades as grades_module
    monkeypatch.setattr(grades_module, "AI_AGENTS_INTERNAL_KEY", "")

    classroom_id, student_id = _setup_classroom_with_enrolled_student()
    resp = client.post(
        "/grades/submit-from-agent",
        json={"student_id": student_id, "classroom_id": classroom_id, "score_0_to_1": 0.5, "feedback": "x"},
        headers={"X-Internal-Service-Key": "cualquier-cosa"},
    )
    assert resp.status_code == 503

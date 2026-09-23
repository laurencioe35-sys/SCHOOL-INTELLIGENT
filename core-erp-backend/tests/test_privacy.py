"""
Tests de compliance de datos de menores.

Corre contra la misma base Postgres real de pruebas que el resto de la
suite (ver tests/test_erp.py). Cada test registra sus propios usuarios
con emails únicos para no chocar entre tests dentro del mismo archivo.
"""
import os

os.environ["ERP_DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/erp_educativo_test"
os.environ["ERP_REDIS_URL"] = "redis://localhost:6379/1"
os.environ.setdefault("ERP_SECRET_KEY", "test_secret_key")

import pytest
from datetime import date
from fastapi.testclient import TestClient

from database.connection import engine
from database.models import Base
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    import redis
    r = redis.from_url(os.environ["ERP_REDIS_URL"])
    r.flushdb()
    yield


def _register(email, role="student", organization_name="Colegio Privacidad", **extra):
    payload = {
        "full_name": "Usuario Test", "email": email, "password": "clave123",
        "role": role, "organization_name": organization_name, **extra,
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _admin_token(org="Colegio Privacidad"):
    return _register("admin@test.pe", role="admin", organization_name=org)


def _teacher_token(org="Colegio Privacidad"):
    return _register("teacher@test.pe", role="teacher", organization_name=org)


def _minor_student(org="Colegio Privacidad", email="menor@test.pe"):
    """Alumno con fecha de nacimiento que lo hace menor bajo el umbral
    por defecto (14 años) — nace hace 10 años."""
    ten_years_ago = date(date.today().year - 10, 1, 1)
    token = _register(email, organization_name=org, date_of_birth=ten_years_ago.isoformat())
    import base64, json as jsonlib
    payload_b64 = token.split(".")[0]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    student_id = jsonlib.loads(base64.urlsafe_b64decode(payload_b64))["sub"]
    return student_id


def _create_classroom(teacher_headers, org="Colegio Privacidad"):
    resp = client.post("/classrooms", json={"name": "Aula 1"}, headers=teacher_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_registering_a_minor_stores_date_of_birth_and_is_minor_true():
    admin_token = _admin_token()
    student_id = _minor_student()

    resp = client.get(f"/privacy/consent/{student_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["is_minor"] is True


def test_enrollment_blocked_without_parental_consent_for_minor():
    teacher_token = _teacher_token()
    teacher_headers = {"Authorization": f"Bearer {teacher_token}"}
    classroom_id = _create_classroom(teacher_headers)
    student_id = _minor_student()

    resp = client.post("/students/enroll", json={"student_id": student_id, "classroom_id": classroom_id}, headers=teacher_headers)
    assert resp.status_code == 403
    assert "consentimiento parental" in resp.json()["detail"]


def test_enrollment_succeeds_after_consent_granted():
    teacher_token = _teacher_token()
    teacher_headers = {"Authorization": f"Bearer {teacher_token}"}
    classroom_id = _create_classroom(teacher_headers)
    student_id = _minor_student()

    consent_resp = client.post("/privacy/consent", json={
        "student_id": student_id, "guardian_full_name": "Mama Test",
        "guardian_email": "mama@test.pe", "consent_type": "data_processing",
    }, headers=teacher_headers)
    assert consent_resp.status_code == 200, consent_resp.text

    resp = client.post("/students/enroll", json={"student_id": student_id, "classroom_id": classroom_id}, headers=teacher_headers)
    assert resp.status_code == 200, resp.text


def test_revoked_consent_blocks_new_enrollment_again():
    teacher_token = _teacher_token()
    teacher_headers = {"Authorization": f"Bearer {teacher_token}"}
    classroom_id_1 = _create_classroom(teacher_headers)
    student_id = _minor_student()

    consent_resp = client.post("/privacy/consent", json={
        "student_id": student_id, "guardian_full_name": "Mama Test",
        "guardian_email": "mama@test.pe",
    }, headers=teacher_headers)
    consent_id = consent_resp.json()["id"]

    revoke_resp = client.delete(f"/privacy/consent/{consent_id}", headers=teacher_headers)
    assert revoke_resp.status_code == 200

    resp = client.post("/students/enroll", json={"student_id": student_id, "classroom_id": classroom_id_1}, headers=teacher_headers)
    assert resp.status_code == 403


def test_adult_student_enrollment_not_blocked_by_consent():
    """Un alumno SIN fecha de nacimiento registrada (is_minor() -> None)
    no debe bloquearse — solo se exige consentimiento cuando se CONFIRMA
    que es menor, no ante la ausencia del dato."""
    teacher_token = _teacher_token()
    teacher_headers = {"Authorization": f"Bearer {teacher_token}"}
    classroom_id = _create_classroom(teacher_headers)
    student_token = _register("adulto@test.pe")
    import base64, json as jsonlib
    payload_b64 = student_token.split(".")[0]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    student_id = jsonlib.loads(base64.urlsafe_b64decode(payload_b64))["sub"]

    resp = client.post("/students/enroll", json={"student_id": student_id, "classroom_id": classroom_id}, headers=teacher_headers)
    assert resp.status_code == 200, resp.text


def test_data_export_includes_grades_and_consent_history():
    teacher_token = _teacher_token()
    teacher_headers = {"Authorization": f"Bearer {teacher_token}"}
    student_id = _minor_student()

    client.post("/privacy/consent", json={
        "student_id": student_id, "guardian_full_name": "Mama Test", "guardian_email": "mama@test.pe",
    }, headers=teacher_headers)

    resp = client.get(f"/privacy/export/{student_id}", headers=teacher_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["student"]["id"] == student_id
    assert len(data["consent_history"]) == 1
    assert data["consent_history"][0]["consent_type"] == "data_processing"


def test_student_can_export_own_data_but_not_others():
    admin_token = _admin_token()
    student_id = _minor_student(email="self_export@test.pe")

    student_login = client.post("/auth/login", json={"email": "self_export@test.pe", "password": "clave123"})
    student_token = student_login.json()["access_token"]

    own = client.get(f"/privacy/export/{student_id}", headers={"Authorization": f"Bearer {student_token}"})
    assert own.status_code == 200

    other_student_id = _minor_student(email="otro@test.pe")
    forbidden = client.get(f"/privacy/export/{other_student_id}", headers={"Authorization": f"Bearer {student_token}"})
    assert forbidden.status_code == 403


def test_erase_data_anonymizes_and_blocks_login():
    admin_token = _admin_token()
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    student_id = _minor_student(email="borrar@test.pe")

    resp = client.delete(f"/privacy/data/{student_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "anonymized"

    # El correo original ya no debe poder usarse para iniciar sesión.
    login = client.post("/auth/login", json={"email": "borrar@test.pe", "password": "clave123"})
    assert login.status_code == 401


def test_erase_data_requires_admin_role():
    teacher_token = _teacher_token()
    student_id = _minor_student(email="proteger@test.pe")

    resp = client.delete(f"/privacy/data/{student_id}", headers={"Authorization": f"Bearer {teacher_token}"})
    assert resp.status_code == 403


def test_minor_data_access_is_audited():
    """Exportar los datos de un alumno MENOR debe dejar rastro en
    DataAccessAuditLog — verificado directamente contra la tabla, no solo
    contra la respuesta del endpoint."""
    teacher_token = _teacher_token()
    student_id = _minor_student(email="auditado@test.pe")

    client.get(f"/privacy/export/{student_id}", headers={"Authorization": f"Bearer {teacher_token}"})

    from database.connection import SessionLocal
    from database.models import DataAccessAuditLog, DataAccessAction
    db = SessionLocal()
    try:
        logs = db.query(DataAccessAuditLog).filter(
            DataAccessAuditLog.subject_student_id == student_id,
            DataAccessAuditLog.action == DataAccessAction.export_data,
        ).all()
        assert len(logs) == 1
    finally:
        db.close()

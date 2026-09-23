"""
Tests de integración del backend ERP.

Corren contra la MISMA base Postgres real usada en desarrollo (no un mock),
en una base separada `erp_educativo_test` para no pisar datos de desarrollo.
Cada test limpia las tablas relevantes al inicio.

Correr con: pytest -v (desde core-erp-backend/, con Postgres y Redis corriendo)
"""
import os

os.environ["ERP_DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/erp_educativo_test"
os.environ["ERP_REDIS_URL"] = "redis://localhost:6379/1"  # DB 1, separada de la de desarrollo

import pytest
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


def register_teacher(organization_name="Colegio Test"):
    resp = client.post("/auth/register", json={
        "full_name": "Prof. Test", "email": "teacher@test.pe", "password": "clave123",
        "role": "teacher", "organization_name": organization_name,
    })
    assert resp.status_code == 200
    return resp.json()["access_token"]


def register_student(organization_name="Colegio Test"):
    resp = client.post("/auth/register", json={
        "full_name": "Alumno Test", "email": "student@test.pe", "password": "clave123",
        "organization_name": organization_name,
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    import base64, json as jsonlib
    payload_b64 = token.split(".")[0]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = jsonlib.loads(base64.urlsafe_b64decode(payload_b64))
    return payload["sub"]


def test_register_and_login():
    client.post("/auth/register", json={
        "full_name": "Ana", "email": "ana@test.pe", "password": "clave123", "organization_name": "Colegio Ana",
    })
    resp = client.post("/auth/login", json={"email": "ana@test.pe", "password": "clave123"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password_fails():
    client.post("/auth/register", json={
        "full_name": "Ana", "email": "ana2@test.pe", "password": "clave123", "organization_name": "Colegio Ana",
    })
    resp = client.post("/auth/login", json={"email": "ana2@test.pe", "password": "incorrecta"})
    assert resp.status_code == 401


def test_student_cannot_create_classroom():
    resp = client.post("/auth/register", json={
        "full_name": "Alumno", "email": "alumno@test.pe", "password": "clave123", "organization_name": "Colegio Ana",
    })
    token = resp.json()["access_token"]
    resp = client.post("/classrooms", json={"name": "Aula X"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_multi_tenant_isolation_classrooms_not_visible_across_orgs():
    """Un profesor del Colegio A no debe ver ni poder operar sobre aulas
    del Colegio B, aunque conozca el UUID exacto del aula."""
    token_a = register_teacher(organization_name="Colegio A")
    classroom_a_id = client.post(
        "/classrooms", json={"name": "Aula del Colegio A"}, headers={"Authorization": f"Bearer {token_a}"}
    ).json()["id"]

    resp = client.post("/auth/register", json={
        "full_name": "Prof. B", "email": "teacherb@test.pe", "password": "clave123",
        "role": "teacher", "organization_name": "Colegio B",
    })
    token_b = resp.json()["access_token"]

    # El profesor B crea su propia aula.
    client.post("/classrooms", json={"name": "Aula del Colegio B"}, headers={"Authorization": f"Bearer {token_b}"})

    # El profesor B lista aulas: NO debe ver la del Colegio A.
    resp = client.get("/classrooms", headers={"Authorization": f"Bearer {token_b}"})
    classroom_names = [c["name"] for c in resp.json()]
    assert "Aula del Colegio A" not in classroom_names
    assert "Aula del Colegio B" in classroom_names

    # El profesor B intenta iniciar la clase del Colegio A directamente
    # por UUID: debe recibir 404 (no 403 — ni siquiera debe confirmar que
    # el aula existe, para no filtrar información entre organizaciones).
    resp = client.post(f"/classrooms/{classroom_a_id}/start", headers={"Authorization": f"Bearer {token_b}"})
    assert resp.status_code == 404


def test_teacher_can_create_and_start_classroom():
    token = register_teacher()
    resp = client.post("/classrooms", json={"name": "Aula X"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    classroom_id = resp.json()["id"]

    resp = client.post(f"/classrooms/{classroom_id}/start", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_grade_submit_requires_active_enrollment():
    """Antes de este fix, se podía enviar una nota para CUALQUIER
    student_id sin verificar matrícula — el error solo aparecía después,
    en el batch worker. Ahora se rechaza de inmediato al enviarla."""
    token = register_teacher()
    classroom_id = client.post(
        "/classrooms", json={"name": "Aula X"}, headers={"Authorization": f"Bearer {token}"}
    ).json()["id"]
    student_id = register_student()  # registrado, pero NO matriculado en esta aula

    resp = client.post(
        "/grades/submit",
        json={"student_id": student_id, "classroom_id": classroom_id, "score": 18},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "matriculado" in resp.json()["detail"]


def test_grade_submit_and_batch_consolidation_valid_student():
    token = register_teacher()
    student_id = register_student()
    classroom_id = client.post(
        "/classrooms", json={"name": "Aula X"}, headers={"Authorization": f"Bearer {token}"}
    ).json()["id"]

    # Matricular al alumno ANTES de poder enviarle notas (comportamiento nuevo).
    resp = client.post(
        "/students/enroll",
        json={"student_id": student_id, "classroom_id": classroom_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    resp = client.post(
        "/grades/submit",
        json={"student_id": student_id, "classroom_id": classroom_id, "score": 18},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["queue_length"] == 1

    from workers.batch_db_worker import run_once
    count = run_once()
    assert count == 1


def test_grade_with_corrupt_event_in_redis_goes_to_dead_letter_not_crash():
    """Regresión: un evento corrupto que llegara a Redis por una vía que
    no sea el endpoint validado (ej. otro microservicio, un bug, o un
    reintento con datos viejos) no debe tumbar el batch worker ni
    perderse silenciosamente. Se inyecta directo a Redis para simular
    ese caso, sin pasar por /grades/submit (que ya lo bloquearía)."""
    token = register_teacher()
    classroom_id = client.post(
        "/classrooms", json={"name": "Aula X"}, headers={"Authorization": f"Bearer {token}"}
    ).json()["id"]

    import redis
    import json as jsonlib
    r = redis.from_url(os.environ["ERP_REDIS_URL"], decode_responses=True)
    r.rpush("grades:pending", jsonlib.dumps({
        "student_id": "fantasma_no_existe", "classroom_id": classroom_id, "score": 15,
    }))

    from workers.batch_db_worker import run_once
    count = run_once()  # no debe lanzar excepción
    assert count == 0

    dead_letter = r.lrange("grades:dead_letter", 0, -1)
    assert len(dead_letter) == 1
    assert "fantasma_no_existe" in dead_letter[0]


# ---------- Tests de matrícula (students.py) ----------

def test_enroll_student_and_get_profile():
    token = register_teacher()
    student_id = register_student()
    classroom_id = client.post(
        "/classrooms", json={"name": "Aula X"}, headers={"Authorization": f"Bearer {token}"}
    ).json()["id"]

    resp = client.post(
        "/students/enroll",
        json={"student_id": student_id, "classroom_id": classroom_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # Matricularlo de nuevo debe fallar (ya está matriculado).
    resp = client.post(
        "/students/enroll",
        json={"student_id": student_id, "classroom_id": classroom_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400

    # El perfil del alumno debe reflejar el aula, aunque aún sin notas.
    resp = client.get(f"/students/{student_id}/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    profile = resp.json()
    assert classroom_id in profile["classrooms"]
    assert profile["average_score"] is None


def test_student_cannot_see_another_students_profile():
    token = register_teacher()
    student_a_id = register_student()

    resp = client.post("/auth/register", json={
        "full_name": "Alumno B", "email": "alumnob@test.pe", "password": "clave123",
        "organization_name": "Colegio Test",
    })
    student_b_token = resp.json()["access_token"]

    resp = client.get(f"/students/{student_a_id}/profile", headers={"Authorization": f"Bearer {student_b_token}"})
    assert resp.status_code == 403


def test_enrollment_isolated_across_organizations():
    """Un docente no debe poder matricular a un alumno de otra organización,
    ni siquiera conociendo su ID exacto."""
    token_a = register_teacher(organization_name="Colegio A")
    classroom_a_id = client.post(
        "/classrooms", json={"name": "Aula A"}, headers={"Authorization": f"Bearer {token_a}"}
    ).json()["id"]

    resp = client.post("/auth/register", json={
        "full_name": "Alumno B", "email": "alumno_orgb@test.pe", "password": "clave123",
        "organization_name": "Colegio B",
    })
    student_b_id = resp.json()["access_token"]  # placeholder, se decodifica abajo
    import base64, json as jsonlib
    token = resp.json()["access_token"]
    payload_b64 = token.split(".")[0]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    student_b_id = jsonlib.loads(base64.urlsafe_b64decode(payload_b64))["sub"]

    resp = client.post(
        "/students/enroll",
        json={"student_id": student_b_id, "classroom_id": classroom_a_id},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 404  # el alumno "no existe" desde la perspectiva del Colegio A


# ---------- Tests de facturación (billing.py) ----------

def test_create_and_pay_invoice():
    token = register_teacher()
    student_id = register_student()

    resp = client.post(
        "/billing/invoices",
        json={
            "student_id": student_id, "concept": "Pensión Julio 2026",
            "amount_cents": 35000, "due_date": "2026-07-31T00:00:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    invoice = resp.json()
    assert invoice["status"] == "pending"
    invoice_id = invoice["id"]

    resp = client.post(
        f"/billing/invoices/{invoice_id}/pay",
        json={"payment_method_token": "tok_test_visa_4242"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    paid = resp.json()
    assert paid["status"] == "paid"
    assert paid["payment_reference"].startswith("MOCK-")

    # Pagarla de nuevo debe fallar.
    resp = client.post(
        f"/billing/invoices/{invoice_id}/pay",
        json={"payment_method_token": "tok_test_visa_4242"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_student_cannot_pay_another_students_invoice():
    token = register_teacher()
    student_a_id = register_student()

    invoice_id = client.post(
        "/billing/invoices",
        json={
            "student_id": student_a_id, "concept": "Pensión Julio 2026",
            "amount_cents": 35000, "due_date": "2026-07-31T00:00:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]

    resp = client.post("/auth/register", json={
        "full_name": "Alumno B", "email": "alumnob2@test.pe", "password": "clave123",
        "organization_name": "Colegio Test",
    })
    student_b_token = resp.json()["access_token"]

    resp = client.post(
        f"/billing/invoices/{invoice_id}/pay",
        json={"payment_method_token": "tok_test_visa_4242"},
        headers={"Authorization": f"Bearer {student_b_token}"},
    )
    assert resp.status_code == 403


def test_overdue_invoices_detection():
    token = register_teacher()
    student_id = register_student()

    # Factura con fecha de vencimiento en el pasado.
    client.post(
        "/billing/invoices",
        json={
            "student_id": student_id, "concept": "Pensión Enero 2026 (vencida)",
            "amount_cents": 35000, "due_date": "2026-01-31T00:00:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get("/billing/invoices/overdue", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    overdue = resp.json()
    assert len(overdue) == 1
    assert overdue[0]["status"] == "overdue"


# ---------- Tests de revocación de tokens (logout) ----------

def test_token_works_before_logout_and_fails_after():
    token = register_teacher()

    # Antes del logout: funciona normalmente.
    resp = client.post("/classrooms", json={"name": "Aula X"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    # Logout: revoca el token.
    resp = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "logged_out"

    # Después del logout: el MISMO token ya no debe funcionar, en ningún endpoint.
    resp = client.post("/classrooms", json={"name": "Aula Y"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401

    resp = client.get("/classrooms", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_logout_twice_with_same_token_fails_gracefully():
    """Un logout repetido con un token ya revocado no debe tumbar el
    servidor ni comportarse de forma inesperada."""
    token = register_teacher()
    resp = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    resp = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_different_tokens_from_same_user_are_independent():
    """Revocar un token (ej. logout desde el celular) no debe invalidar
    otra sesión activa del mismo usuario (ej. seguir logueado en la PC) —
    cada jti es independiente."""
    token_a = register_teacher()  # sesión 1 (ej. celular)

    login_resp = client.post("/auth/login", json={"email": "teacher@test.pe", "password": "clave123"})
    token_b = login_resp.json()["access_token"]  # sesión 2 (ej. PC), mismo usuario

    assert token_a != token_b  # deben ser tokens distintos (jti distinto)

    # Cerrar la sesión 1 no debe afectar la sesión 2.
    client.post("/auth/logout", headers={"Authorization": f"Bearer {token_a}"})

    resp = client.get("/classrooms", headers={"Authorization": f"Bearer {token_b}"})
    assert resp.status_code == 200

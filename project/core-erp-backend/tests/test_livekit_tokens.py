"""
Tests de la emisión de tokens de LiveKit en api/classrooms.py.

Mintear un token de LiveKit es firmar un JWT localmente (HMAC) — NO
requiere red ni un servidor LiveKit corriendo, así que esto SÍ se puede
probar de punta a punta en este entorno, a diferencia del resto del flujo
de video (VideoMixer.tsx conectándose de verdad a una sala), que sigue
necesitando infraestructura real (ver
multimedia-stream-server/streaming/webrtc_handler.ts).
"""
import os

os.environ["ERP_DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/erp_educativo_test"
os.environ["ERP_REDIS_URL"] = "redis://localhost:6379/1"

import jwt
import pytest
from fastapi.testclient import TestClient

from database.connection import engine
from database.models import Base
from main import app
import api.classrooms as classrooms_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def livekit_enabled(monkeypatch):
    monkeypatch.setattr(classrooms_module, "LIVEKIT_API_KEY", "devkey")
    monkeypatch.setattr(classrooms_module, "LIVEKIT_API_SECRET", "devsecret")
    monkeypatch.setattr(classrooms_module, "LIVEKIT_WS_URL", "wss://livekit.tu-dominio.edu.pe")


def register_teacher(organization_name="Colegio LiveKit"):
    resp = client.post("/auth/register", json={
        "full_name": "Prof. LiveKit", "email": "teacher-lk@test.pe", "password": "clave123",
        "role": "teacher", "organization_name": organization_name,
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    import base64, json as jsonlib
    payload_b64 = token.split(".")[0]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    teacher_id = jsonlib.loads(base64.urlsafe_b64decode(payload_b64))["sub"]
    return token, teacher_id


def register_student(organization_name="Colegio LiveKit"):
    resp = client.post("/auth/register", json={
        "full_name": "Alumno LiveKit", "email": "student-lk@test.pe", "password": "clave123",
        "organization_name": organization_name,
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    import base64, json as jsonlib
    payload_b64 = token.split(".")[0]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    student_id = jsonlib.loads(base64.urlsafe_b64decode(payload_b64))["sub"]
    return token, student_id


def test_start_session_without_livekit_configured_returns_no_token():
    """Estado por defecto en este entorno: sin cuenta de LiveKit, la
    sesión igual se crea (pizarra/CRDT siguen funcionando) pero sin
    credenciales de video."""
    teacher_token, _ = register_teacher()
    classroom_id = client.post(
        "/classrooms", json={"name": "Aula sin LiveKit"}, headers={"Authorization": f"Bearer {teacher_token}"}
    ).json()["id"]

    resp = client.post(f"/classrooms/{classroom_id}/start", headers={"Authorization": f"Bearer {teacher_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["livekit_token"] is None
    assert body["livekit_ws_url"] is None


def test_start_session_mints_valid_publisher_token_for_teacher(livekit_enabled):
    teacher_token, teacher_id = register_teacher()
    classroom_id = client.post(
        "/classrooms", json={"name": "Aula con LiveKit"}, headers={"Authorization": f"Bearer {teacher_token}"}
    ).json()["id"]

    resp = client.post(f"/classrooms/{classroom_id}/start", headers={"Authorization": f"Bearer {teacher_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["livekit_ws_url"] == "wss://livekit.tu-dominio.edu.pe"

    decoded = jwt.decode(body["livekit_token"], "devsecret", algorithms=["HS256"])
    assert decoded["sub"] == teacher_id
    assert decoded["iss"] == "devkey"
    assert decoded["video"]["room"] == f"classroom-{classroom_id}"
    assert decoded["video"]["roomJoin"] is True
    assert decoded["video"]["canPublish"] is True


def test_join_token_rejects_when_classroom_not_live(livekit_enabled):
    teacher_token, _ = register_teacher()
    classroom_id = client.post(
        "/classrooms", json={"name": "Aula quieta"}, headers={"Authorization": f"Bearer {teacher_token}"}
    ).json()["id"]

    resp = client.post(f"/classrooms/{classroom_id}/join-token", headers={"Authorization": f"Bearer {teacher_token}"})
    assert resp.status_code == 400


def test_join_token_rejects_unenrolled_student(livekit_enabled):
    teacher_token, _ = register_teacher()
    student_token, _ = register_student()
    classroom_id = client.post(
        "/classrooms", json={"name": "Aula en vivo"}, headers={"Authorization": f"Bearer {teacher_token}"}
    ).json()["id"]
    client.post(f"/classrooms/{classroom_id}/start", headers={"Authorization": f"Bearer {teacher_token}"})

    # El alumno NO está matriculado en esta aula.
    resp = client.post(f"/classrooms/{classroom_id}/join-token", headers={"Authorization": f"Bearer {student_token}"})
    assert resp.status_code == 403


def test_join_token_gives_enrolled_student_subscriber_only_grant(livekit_enabled):
    teacher_token, _ = register_teacher()
    student_token, student_id = register_student()
    classroom_id = client.post(
        "/classrooms", json={"name": "Aula en vivo"}, headers={"Authorization": f"Bearer {teacher_token}"}
    ).json()["id"]
    client.post(f"/classrooms/{classroom_id}/start", headers={"Authorization": f"Bearer {teacher_token}"})

    resp = client.post(
        "/students/enroll",
        json={"student_id": student_id, "classroom_id": classroom_id},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 200

    resp = client.post(f"/classrooms/{classroom_id}/join-token", headers={"Authorization": f"Bearer {student_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["can_publish"] is False

    decoded = jwt.decode(body["token"], "devsecret", algorithms=["HS256"])
    assert decoded["video"]["canPublish"] is False
    assert decoded["video"]["canSubscribe"] is True
    assert decoded["video"]["room"] == f"classroom-{classroom_id}"


def test_join_token_without_livekit_configured_fails_closed():
    teacher_token, _ = register_teacher()
    classroom_id = client.post(
        "/classrooms", json={"name": "Aula sin video"}, headers={"Authorization": f"Bearer {teacher_token}"}
    ).json()["id"]
    client.post(f"/classrooms/{classroom_id}/start", headers={"Authorization": f"Bearer {teacher_token}"})

    resp = client.post(f"/classrooms/{classroom_id}/join-token", headers={"Authorization": f"Bearer {teacher_token}"})
    assert resp.status_code == 503

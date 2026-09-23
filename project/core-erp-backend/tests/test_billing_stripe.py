"""
Tests de la integración real de Stripe en api/billing.py.

Se mockea únicamente la llamada de red (`stripe.PaymentIntent.create`) —
el mismo límite exacto que tests/test_llm_client.py mockea para el
proveedor LLM real (`_call_anthropic`). No hay credenciales de Stripe
reales en este entorno, así que no se ejercita la red; sí se ejercita
toda la lógica de este archivo: selección de proveedor, manejo de
rechazo de tarjeta, errores de la pasarela y el bloqueo explícito de
monedas no soportadas (PEN).
"""
import os

os.environ["ERP_DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/erp_educativo_test"
os.environ["ERP_REDIS_URL"] = "redis://localhost:6379/1"

import stripe
import pytest
from fastapi.testclient import TestClient

from database.connection import engine
from database.models import Base
from main import app
import api.billing as billing_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    import redis
    r = redis.from_url(os.environ["ERP_REDIS_URL"])
    r.flushdb()
    yield


@pytest.fixture
def stripe_enabled(monkeypatch):
    """Activa el modo 'gateway real' sin tocar la red — monkeypatchea
    las constantes del módulo ya importado, igual que se hace con
    AI_AGENTS_INTERNAL_KEY en test_grading_agent_integration.py."""
    monkeypatch.setattr(billing_module, "USE_REAL_PAYMENT_GATEWAY", True)
    monkeypatch.setattr(billing_module, "PAYMENT_GATEWAY_API_KEY", "sk_test_fake")
    monkeypatch.setattr(billing_module, "PAYMENT_GATEWAY_PROVIDER", "stripe")


def register_teacher(organization_name="Colegio Stripe"):
    resp = client.post("/auth/register", json={
        "full_name": "Prof. Stripe", "email": "teacher-stripe@test.pe", "password": "clave123",
        "role": "teacher", "organization_name": organization_name,
    })
    assert resp.status_code == 200
    return resp.json()["access_token"]


def register_student(organization_name="Colegio Stripe"):
    resp = client.post("/auth/register", json={
        "full_name": "Alumno Stripe", "email": "student-stripe@test.pe", "password": "clave123",
        "organization_name": organization_name,
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    import base64, json as jsonlib
    payload_b64 = token.split(".")[0]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = jsonlib.loads(base64.urlsafe_b64decode(payload_b64))
    return payload["sub"]


def _create_invoice(teacher_token, student_id, currency="USD"):
    resp = client.post(
        "/billing/invoices",
        json={
            "student_id": student_id, "concept": "Pensión julio",
            "amount_cents": 15000, "currency": currency,
            "due_date": "2026-08-01T00:00:00Z",
        },
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def test_stripe_charge_succeeds(monkeypatch, stripe_enabled):
    teacher_token = register_teacher()
    student_id = register_student()
    invoice_id = _create_invoice(teacher_token, student_id, currency="USD")

    class _FakeIntent:
        id = "pi_fake_123"
        status = "succeeded"

    def _fake_create(**kwargs):
        assert kwargs["amount"] == 15000
        assert kwargs["currency"] == "usd"
        assert kwargs["payment_method"] == "pm_card_visa"
        return _FakeIntent()

    monkeypatch.setattr(stripe.PaymentIntent, "create", staticmethod(_fake_create))

    resp = client.post(
        f"/billing/invoices/{invoice_id}/pay",
        json={"payment_method_token": "pm_card_visa"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "paid"
    assert body["payment_reference"] == "pi_fake_123"


def test_stripe_card_decline_returns_402(monkeypatch, stripe_enabled):
    teacher_token = register_teacher()
    student_id = register_student()
    invoice_id = _create_invoice(teacher_token, student_id, currency="USD")

    def _fake_create(**kwargs):
        raise stripe.error.CardError(
            message="Tu tarjeta fue rechazada.", param=None, code="card_declined",
        )

    monkeypatch.setattr(stripe.PaymentIntent, "create", staticmethod(_fake_create))

    resp = client.post(
        f"/billing/invoices/{invoice_id}/pay",
        json={"payment_method_token": "pm_card_declined"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 402


def test_stripe_api_error_returns_502(monkeypatch, stripe_enabled):
    teacher_token = register_teacher()
    student_id = register_student()
    invoice_id = _create_invoice(teacher_token, student_id, currency="USD")

    def _fake_create(**kwargs):
        raise stripe.error.APIConnectionError(message="timeout hablando con Stripe")

    monkeypatch.setattr(stripe.PaymentIntent, "create", staticmethod(_fake_create))

    resp = client.post(
        f"/billing/invoices/{invoice_id}/pay",
        json={"payment_method_token": "pm_card_visa"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 502


def test_pen_currency_rejected_for_stripe_before_calling_stripe(monkeypatch, stripe_enabled):
    """PEN (pensiones en soles, el caso de uso real de este ERP) no lo
    soporta Stripe — debe rechazarse ANTES de intentar la llamada, con un
    mensaje que indique la alternativa (Culqi/Niubiz)."""
    teacher_token = register_teacher()
    student_id = register_student()
    invoice_id = _create_invoice(teacher_token, student_id, currency="PEN")

    def _fake_create(**kwargs):
        raise AssertionError("no debería llamarse a Stripe para una moneda no soportada")

    monkeypatch.setattr(stripe.PaymentIntent, "create", staticmethod(_fake_create))

    resp = client.post(
        f"/billing/invoices/{invoice_id}/pay",
        json={"payment_method_token": "pm_card_visa"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 422
    assert "Culqi" in resp.json()["detail"]


def test_unsupported_provider_raises_not_implemented(monkeypatch, stripe_enabled):
    monkeypatch.setattr(billing_module, "PAYMENT_GATEWAY_PROVIDER", "culqi")
    teacher_token = register_teacher()
    student_id = register_student()
    invoice_id = _create_invoice(teacher_token, student_id, currency="PEN")

    with pytest.raises(NotImplementedError):
        client.post(
            f"/billing/invoices/{invoice_id}/pay",
            json={"payment_method_token": "tkn_culqi"},
            headers={"Authorization": f"Bearer {teacher_token}"},
        )


def test_mock_gateway_still_used_when_no_api_key_configured():
    """Regresión: sin PAYMENT_GATEWAY_API_KEY (el estado por defecto en
    este entorno de desarrollo), el flujo mock de siempre sigue vivo."""
    teacher_token = register_teacher()
    student_id = register_student()
    invoice_id = _create_invoice(teacher_token, student_id, currency="PEN")

    resp = client.post(
        f"/billing/invoices/{invoice_id}/pay",
        json={"payment_method_token": "cualquier-token"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["payment_reference"].startswith("MOCK-")

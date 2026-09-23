from uuid import uuid4

from app.main import app
from app.security import create_access_token
from fastapi.testclient import TestClient


def test_invoice_creation_and_payment_flow():
    client = TestClient(app)
    tenant_id = str(uuid4())
    headers = {"Authorization": f"Bearer {create_access_token(user_id=uuid4(), tenant_id=tenant_id, role='admin')}"}

    student = client.post(
        "/api/v1/students",
        json={"first_name": "María", "last_name": "García", "document_number": "2001"},
        headers=headers,
    )
    assert student.status_code == 201

    invoice = client.post(
        "/api/v1/billing/invoices",
        json={
            "student_id": student.json()["id"],
            "concept": "Pensión octubre",
            "amount_cents": 250000,
            "currency": "PEN",
            "due_date": "2026-10-15T00:00:00Z",
        },
        headers=headers,
    )
    assert invoice.status_code == 201
    body = invoice.json()
    assert body["status"] == "pending"
    assert body["amount_cents"] == 250000

    paid = client.post(
        "/api/v1/billing/invoices/{}/pay".format(body["id"]),
        json={"payment_method_token": "pm_test_visa_123"},
        headers=headers,
    )
    assert paid.status_code == 200
    payload = paid.json()
    assert payload["status"] == "paid"
    assert payload["payment_reference"].startswith("MOCK-")


def test_invoice_listing_is_scoped_to_tenant():
    client = TestClient(app)
    tenant_id = str(uuid4())
    headers = {"Authorization": f"Bearer {create_access_token(user_id=uuid4(), tenant_id=tenant_id, role='admin')}"}

    student = client.post(
        "/api/v1/students",
        json={"first_name": "Ana", "last_name": "López", "document_number": "2002"},
        headers=headers,
    )
    assert student.status_code == 201

    invoice = client.post(
        "/api/v1/billing/invoices",
        json={
            "student_id": student.json()["id"],
            "concept": "Colegiatura",
            "amount_cents": 150000,
            "currency": "PEN",
            "due_date": "2026-11-15T00:00:00Z",
        },
        headers=headers,
    )
    assert invoice.status_code == 201

    listed = client.get("/api/v1/billing/invoices", headers=headers)
    assert listed.status_code == 200
    payload = listed.json()
    assert len(payload) >= 1
    assert any(item["id"] == invoice.json()["id"] for item in payload)
    assert all(item["tenant_id"] == tenant_id for item in payload)

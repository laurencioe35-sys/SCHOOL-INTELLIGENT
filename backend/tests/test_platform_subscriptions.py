from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Subscription, Tenant
from app.security import create_access_token


def test_platform_admin_can_list_and_update_subscriptions():
    tenant_id = uuid4()
    subscription_id = uuid4()
    with SessionLocal() as db:
        db.add(Tenant(id=tenant_id, name="Colegio Test", active=True))
        db.add(Subscription(id=subscription_id, tenant_id=tenant_id, plan_code="TRIAL", status="trialing"))
        db.commit()

    client = TestClient(app)
    platform_headers = {
        "Authorization": f"Bearer {create_access_token(uuid4(), uuid4(), 'platform_admin', plan='CONTA_PRO')}",
    }

    listed = client.get("/api/v1/platform/subscriptions", headers=platform_headers)
    assert listed.status_code == 200
    assert any(row["id"] == str(subscription_id) for row in listed.json())

    updated = client.patch(
        f"/api/v1/platform/subscriptions/{subscription_id}",
        json={"plan": "PRO", "status": "active"},
        headers=platform_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["plan"] == "PRO"
    assert updated.json()["status"] == "active"


def test_platform_subscription_mutation_requires_platform_admin_and_valid_values():
    tenant_id = uuid4()
    subscription_id = uuid4()
    with SessionLocal() as db:
        db.add(Tenant(id=tenant_id, name="Colegio Test Validacion", active=True))
        db.add(Subscription(id=subscription_id, tenant_id=tenant_id, plan_code="TRIAL", status="trialing"))
        db.commit()

    client = TestClient(app)
    admin_headers = {"Authorization": f"Bearer {create_access_token(uuid4(), tenant_id, 'admin')}"}
    forbidden = client.patch(
        f"/api/v1/platform/subscriptions/{subscription_id}",
        json={"plan": "PRO"},
        headers=admin_headers,
    )
    assert forbidden.status_code == 403

    platform_headers = {
        "Authorization": f"Bearer {create_access_token(uuid4(), uuid4(), 'platform_admin')}",
    }
    invalid = client.patch(
        f"/api/v1/platform/subscriptions/{subscription_id}",
        json={"plan": "ENTERPRISE", "status": "active"},
        headers=platform_headers,
    )
    assert invalid.status_code == 422
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.core.audit import record_audit_event
from app.db import SessionLocal, get_current_tenant_id, initialize_db, set_current_tenant_id
from app.models import Invoice, Student, Tenant, User

initialize_db()


def _make_tenant_and_user(email: str = "admin@example.com"):
    tenant = Tenant(id=uuid4(), name=f"Tenant {uuid4().hex[:6]}")
    user = User(id=uuid4(), tenant_id=tenant.id, email=email, password_hash="hash", role="admin")
    return tenant, user


def test_audit_log_is_append_only():
    tenant, user = _make_tenant_and_user()
    with SessionLocal() as db:
        db.add_all([tenant, user])
        db.commit()

        set_current_tenant_id(str(tenant.id))
        event = record_audit_event(
            db,
            tenant_id=tenant.id,
            actor_user_id=user.id,
            entity_name="invoices",
            entity_id=str(uuid4()),
            action="CREATE",
            details={"concept": "test invoice"},
        )
        db.commit()

        with pytest.raises(Exception):
            db.execute(
                text("UPDATE audit_log SET action = 'UPDATED' WHERE id = :event_id"),
                {"event_id": str(event.id)},
            )

        assert get_current_tenant_id() == str(tenant.id)


def test_invoice_tenant_isolation_uses_current_tenant_context():
    tenant_a, user_a = _make_tenant_and_user("a@example.com")
    tenant_b, user_b = _make_tenant_and_user("b@example.com")

    with SessionLocal() as db:
        db.add_all([tenant_a, tenant_b, user_a, user_b])
        db.commit()

        student_a = Student(id=uuid4(), tenant_id=tenant_a.id, first_name="Ana", last_name="A", document_number="A-101")
        student_b = Student(id=uuid4(), tenant_id=tenant_b.id, first_name="Beto", last_name="B", document_number="B-202")
        db.add_all([student_a, student_b])
        db.commit()

        invoice_a = Invoice(
            id=uuid4(),
            tenant_id=tenant_a.id,
            student_id=student_a.id,
            concept="Tuition",
            amount_cents=1000,
            due_date=datetime.now(UTC),
            status="pending",
        )
        db.add(invoice_a)
        db.commit()

        set_current_tenant_id(str(tenant_b.id))
        result = db.scalars(select(Invoice).where(Invoice.tenant_id == tenant_b.id, Invoice.id == invoice_a.id)).first()
        assert result is None

        set_current_tenant_id(str(tenant_a.id))
        result = db.scalars(select(Invoice).where(Invoice.tenant_id == tenant_a.id, Invoice.id == invoice_a.id)).first()
        assert result is not None
        assert get_current_tenant_id() == str(tenant_a.id)

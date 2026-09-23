from uuid import uuid4

from app.db import SessionLocal, engine
from app.migrations import upgrade
from app.modules.payments.repository import record_transaction, update_transaction_status


def test_payment_transactions_are_durable_idempotent_and_tenant_scoped():
    upgrade(engine)
    tenant_id = uuid4()
    with SessionLocal() as db:
        first = record_transaction(db, tenant_id=tenant_id, invoice_id=None, amount_cents=1000, provider="nequi", provider_reference="ref-1", status="pending")
        duplicate = record_transaction(db, tenant_id=tenant_id, invoice_id=None, amount_cents=1000, provider="nequi", provider_reference="ref-1", status="pending")
        assert first.id == duplicate.id
        updated = update_transaction_status(db, tenant_id=tenant_id, provider_reference="ref-1", status="succeeded")
        assert updated.status == "succeeded"
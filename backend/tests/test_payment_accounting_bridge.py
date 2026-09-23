from uuid import uuid4

from app.db import SessionLocal, engine
from app.migrations import upgrade
from app.models import ChartOfAccount, Invoice, JournalEntry, Tenant
from app.modules.payments.reconciliation.accounting_bridge import reconcile_to_accounting
from app.modules.payments.repository import record_transaction


def test_successful_payment_creates_one_balanced_accounting_entry():
    upgrade(engine)
    tenant_id, actor_id, cash_id, receivable_id, invoice_id = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        db.add_all([
            Tenant(id=tenant_id, name="Accounting payments"),
            ChartOfAccount(id=cash_id, tenant_id=tenant_id, code="1105", name="Cash", account_type="asset"),
            ChartOfAccount(id=receivable_id, tenant_id=tenant_id, code="1305", name="Receivable", account_type="asset"),
        ])
        db.commit()
        transaction = record_transaction(db, tenant_id=tenant_id, invoice_id=invoice_id, amount_cents=2500, provider="stripe", provider_reference="ch-1", status="pending")
        reconcile_to_accounting(db, tenant_id=tenant_id, actor_user_id=actor_id, provider_reference=transaction.provider_reference, cash_account_id=cash_id, receivable_account_id=receivable_id, status="pending")
        assert db.query(JournalEntry).filter(JournalEntry.tenant_id == tenant_id).count() == 0
        reconcile_to_accounting(db, tenant_id=tenant_id, actor_user_id=actor_id, provider_reference=transaction.provider_reference, cash_account_id=cash_id, receivable_account_id=receivable_id, status="succeeded")
        reconcile_to_accounting(db, tenant_id=tenant_id, actor_user_id=actor_id, provider_reference=transaction.provider_reference, cash_account_id=cash_id, receivable_account_id=receivable_id, status="succeeded")
        assert db.query(JournalEntry).filter(JournalEntry.tenant_id == tenant_id).count() == 1
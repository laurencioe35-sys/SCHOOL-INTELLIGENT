from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChartOfAccount, JournalEntry, PaymentTransaction
from app.modules.accounting.services.journal_entry_service import create_journal_entry
from app.modules.payments.repository import update_transaction_status


def reconcile_to_accounting(
    db: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    provider_reference: str,
    cash_account_id: UUID,
    receivable_account_id: UUID,
    status: str,
) -> PaymentTransaction:
    transaction = update_transaction_status(
        db,
        tenant_id=tenant_id,
        provider_reference=provider_reference,
        status=status,
    )
    if status != "succeeded" or transaction.invoice_id is None:
        return transaction

    existing_entry = db.scalar(
        select(JournalEntry).where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.entry_number == f"PAY-{provider_reference}",
        )
    )
    if existing_entry:
        return transaction

    accounts = db.scalars(
        select(ChartOfAccount).where(
            ChartOfAccount.tenant_id == tenant_id,
            ChartOfAccount.id.in_([cash_account_id, receivable_account_id]),
        )
    ).all()
    if len(accounts) != 2:
        raise ValueError("Payment accounting accounts must belong to tenant")

    create_journal_entry(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entry_number=f"PAY-{provider_reference}",
        memo=f"Payment reconciliation {provider_reference}",
        lines=[
            {"account_id": cash_account_id, "debit_cents": transaction.amount_cents, "credit_cents": 0},
            {"account_id": receivable_account_id, "debit_cents": 0, "credit_cents": transaction.amount_cents},
        ],
    )
    db.commit()
    return transaction
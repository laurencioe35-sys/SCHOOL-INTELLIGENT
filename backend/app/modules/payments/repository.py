from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PaymentTransaction


def record_transaction(
    db: Session,
    *,
    tenant_id: UUID,
    invoice_id: UUID | None,
    amount_cents: int,
    provider: str,
    provider_reference: str,
    status: str,
) -> PaymentTransaction:
    existing = db.scalar(
        select(PaymentTransaction).where(
            PaymentTransaction.tenant_id == tenant_id,
            PaymentTransaction.provider_reference == provider_reference,
        )
    )
    if existing:
        return existing
    transaction = PaymentTransaction(
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        amount_cents=amount_cents,
        provider=provider,
        provider_reference=provider_reference,
        status=status,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def update_transaction_status(db: Session, *, tenant_id: UUID, provider_reference: str, status: str) -> PaymentTransaction:
    transaction = db.scalar(
        select(PaymentTransaction).where(
            PaymentTransaction.tenant_id == tenant_id,
            PaymentTransaction.provider_reference == provider_reference,
        )
    )
    if transaction is None:
        raise KeyError("Payment transaction not found in tenant")
    transaction.status = status
    db.commit()
    db.refresh(transaction)
    return transaction
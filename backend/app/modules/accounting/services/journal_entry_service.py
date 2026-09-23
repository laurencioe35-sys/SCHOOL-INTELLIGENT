from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.models import ChartOfAccount, JournalEntry, JournalEntryLine


def assert_balanced(lines: list[dict]) -> None:
    debit_total = sum(int(item["debit_cents"]) for item in lines)
    credit_total = sum(int(item["credit_cents"]) for item in lines)
    if debit_total != credit_total:
        raise ValueError("Journal entries must be balanced: debit_total must equal credit_total")


def create_journal_entry(
    db: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    entry_number: str,
    memo: str | None,
    lines: list[dict],
) -> JournalEntry:
    assert_balanced(lines)

    entry = JournalEntry(
        tenant_id=tenant_id,
        entry_number=entry_number,
        memo=memo,
        status="posted",
    )
    db.add(entry)
    db.flush()

    for item in lines:
        account = db.scalar(
            select(ChartOfAccount).where(
                ChartOfAccount.id == item["account_id"],
                ChartOfAccount.tenant_id == tenant_id,
            )
        )
        if account is None:
            raise ValueError("Account not found in tenant")

        db.add(
            JournalEntryLine(
                tenant_id=tenant_id,
                journal_entry_id=entry.id,
                account_id=item["account_id"],
                debit_cents=int(item["debit_cents"]),
                credit_cents=int(item["credit_cents"]),
            )
        )

    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_name="journal_entries",
        entity_id=str(entry.id),
        action="CREATE",
        details={
            "entry_number": entry_number,
            "memo": memo,
            "lines": lines,
        },
    )
    db.flush()
    return entry

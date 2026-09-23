from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.db import get_db
from app.dependencies import tenant_context
from app.models import ChartOfAccount, JournalEntry, JournalEntryLine
from app.security import current_claims

router = APIRouter(prefix="/api/v1/accounting", tags=["accounting"])


@router.post("/chart-of-accounts", status_code=201)
def create_chart_of_account(
    payload: dict,
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    code = str(payload.get("code", "")).strip()
    name = str(payload.get("name", "")).strip()
    account_type = str(payload.get("account_type", "asset")).strip() or "asset"
    if not code or not name:
        raise HTTPException(status_code=400, detail="code and name are required")

    existing = db.scalar(
        select(ChartOfAccount).where(
            ChartOfAccount.tenant_id == tenant_id,
            ChartOfAccount.code == code,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Account code already exists in tenant")

    account = ChartOfAccount(
        tenant_id=tenant_id,
        code=code,
        name=name,
        account_type=account_type,
        active=True,
    )
    db.add(account)
    db.flush()
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=UUID(claims["sub"]),
        entity_name="chart_of_accounts",
        entity_id=str(account.id),
        action="CREATE",
        details={"code": code, "name": name, "account_type": account_type},
    )
    db.commit()
    db.refresh(account)
    return {
        "id": str(account.id),
        "tenant_id": str(account.tenant_id),
        "code": account.code,
        "name": account.name,
        "account_type": account.account_type,
        "active": account.active,
    }


@router.get("/chart-of-accounts")
def list_chart_of_accounts(
    tenant_id: UUID = Depends(tenant_context),
    db: Session = Depends(get_db),
):
    accounts = db.scalars(
        select(ChartOfAccount).where(
            ChartOfAccount.tenant_id == tenant_id,
            ChartOfAccount.active.is_(True),
        )
    ).all()
    return [
        {
            "id": str(account.id),
            "tenant_id": str(account.tenant_id),
            "code": account.code,
            "name": account.name,
            "account_type": account.account_type,
            "active": account.active,
        }
        for account in accounts
    ]


@router.post("/journal-entries", status_code=201)
def create_journal_entry(
    payload: dict,
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    entry_number = str(payload.get("entry_number") or f"JE-{uuid4().hex[:8]}").strip()
    memo = payload.get("memo")
    lines = payload.get("lines") or []
    if not isinstance(lines, list) or not lines:
        raise HTTPException(status_code=400, detail="lines are required")

    total_debit = sum(int(item.get("debit_cents", 0)) for item in lines)
    total_credit = sum(int(item.get("credit_cents", 0)) for item in lines)
    if total_debit != total_credit:
        raise HTTPException(status_code=400, detail="Journal entry must be balanced")

    entry = JournalEntry(
        tenant_id=tenant_id,
        entry_number=entry_number,
        memo=str(memo) if memo is not None else None,
        status="posted",
    )
    db.add(entry)
    db.flush()

    for item in lines:
        account_id = item.get("account_id")
        if not account_id:
            raise HTTPException(status_code=400, detail="Each line needs account_id")
        account = db.scalar(
            select(ChartOfAccount).where(
                ChartOfAccount.id == UUID(str(account_id)),
                ChartOfAccount.tenant_id == tenant_id,
            )
        )
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found in tenant")
        db.add(
            JournalEntryLine(
                tenant_id=tenant_id,
                journal_entry_id=entry.id,
                account_id=account.id,
                debit_cents=int(item.get("debit_cents", 0)),
                credit_cents=int(item.get("credit_cents", 0)),
            )
        )

    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=UUID(claims["sub"]),
        entity_name="journal_entries",
        entity_id=str(entry.id),
        action="CREATE",
        details={"entry_number": entry_number, "memo": memo, "lines": lines},
    )
    db.commit()
    db.refresh(entry)
    return {
        "id": str(entry.id),
        "tenant_id": str(entry.tenant_id),
        "entry_number": entry.number if hasattr(entry, "number") else entry_number,
        "memo": entry.memo,
        "status": entry.status,
        "lines": [
            {
                "account_id": str(line.account_id),
                "debit_cents": line.debit_cents,
                "credit_cents": line.credit_cents,
            }
            for line in db.scalars(select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry.id)).all()
        ],
    }


@router.get("/trial-balance")
def trial_balance(
    tenant_id: UUID = Depends(tenant_context),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(
            JournalEntryLine.account_id,
            ChartOfAccount.code,
            ChartOfAccount.name,
            (
                func.coalesce(func.sum(JournalEntryLine.debit_cents), 0)
                - func.coalesce(func.sum(JournalEntryLine.credit_cents), 0)
            ).label("balance_cents"),
        )
        .join(ChartOfAccount, ChartOfAccount.id == JournalEntryLine.account_id)
        .where(
            JournalEntryLine.tenant_id == tenant_id,
            ChartOfAccount.tenant_id == tenant_id,
        )
        .group_by(JournalEntryLine.account_id, ChartOfAccount.code, ChartOfAccount.name)
    ).all()
    return [
        {
            "account_id": str(item.account_id),
            "code": item.code,
            "name": item.name,
            "balance_cents": item.balance_cents,
        }
        for item in rows
    ]

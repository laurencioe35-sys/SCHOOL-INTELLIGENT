from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import WhiteboardOperation


def append_operation(
    db: Session,
    *,
    tenant_id: UUID,
    room_id: str,
    operation_id: str,
    actor_id: str,
    operation_type: str,
    payload: dict[str, object],
) -> WhiteboardOperation:
    operation = WhiteboardOperation(
        tenant_id=tenant_id,
        room_id=room_id,
        operation_id=operation_id,
        actor_id=actor_id,
        operation_type=operation_type,
        payload=json.dumps(payload, sort_keys=True),
    )
    db.add(operation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(WhiteboardOperation).where(
                WhiteboardOperation.tenant_id == tenant_id,
                WhiteboardOperation.room_id == room_id,
                WhiteboardOperation.operation_id == operation_id,
            )
        )
        if existing is None:
            raise
        return existing
    db.refresh(operation)
    return operation


def list_operations(db: Session, *, tenant_id: UUID, room_id: str) -> list[WhiteboardOperation]:
    return list(
        db.scalars(
            select(WhiteboardOperation)
            .where(WhiteboardOperation.tenant_id == tenant_id, WhiteboardOperation.room_id == room_id)
            .order_by(WhiteboardOperation.created_at, WhiteboardOperation.id)
        )
    )
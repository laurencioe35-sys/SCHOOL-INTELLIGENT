from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LessonEvent


def append_lesson_event(
    db: Session,
    *,
    tenant_id: UUID,
    lesson_id: str,
    event_type: str,
    t_offset_ms: int,
    payload: dict[str, object],
) -> LessonEvent:
    if t_offset_ms < 0:
        raise ValueError("Event offset cannot be negative")
    event = LessonEvent(
        tenant_id=tenant_id,
        lesson_id=lesson_id,
        event_type=event_type,
        t_offset_ms=t_offset_ms,
        payload=json.dumps(payload, sort_keys=True),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_lesson_events(db: Session, *, tenant_id: UUID, lesson_id: str) -> list[LessonEvent]:
    return list(
        db.scalars(
            select(LessonEvent)
            .where(LessonEvent.tenant_id == tenant_id, LessonEvent.lesson_id == lesson_id)
            .order_by(LessonEvent.t_offset_ms, LessonEvent.created_at)
        )
    )
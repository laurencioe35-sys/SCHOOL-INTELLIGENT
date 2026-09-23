from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LiveClassAttendanceRecord, LiveClassRecord


def create_live_class(db: Session, *, tenant_id: UUID, course_id: UUID, teacher_user_id: UUID) -> LiveClassRecord:
    live_class = LiveClassRecord(tenant_id=tenant_id, course_id=course_id, teacher_user_id=teacher_user_id, status="scheduled")
    db.add(live_class)
    db.commit()
    db.refresh(live_class)
    return live_class


def record_attendance(db: Session, *, tenant_id: UUID, live_class_id: UUID, student_id: UUID, status: str, connected_minutes: int, interaction_events: int) -> LiveClassAttendanceRecord:
    existing = db.scalar(select(LiveClassAttendanceRecord).where(LiveClassAttendanceRecord.tenant_id == tenant_id, LiveClassAttendanceRecord.live_class_id == live_class_id, LiveClassAttendanceRecord.student_id == student_id))
    if existing:
        existing.attendance_status = status
        existing.connected_minutes = connected_minutes
        existing.interaction_events = interaction_events
        db.commit()
        return existing
    record = LiveClassAttendanceRecord(tenant_id=tenant_id, live_class_id=live_class_id, student_id=student_id, attendance_status=status, connected_minutes=connected_minutes, interaction_events=interaction_events)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
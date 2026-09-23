from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AdmissionApplication, AdmissionWaitlistEntry


def next_waitlist_position(db: Session, tenant_id: UUID, grade_level_code: str) -> int:
    count = db.scalar(
        select(func.count(AdmissionWaitlistEntry.id)).where(
            AdmissionWaitlistEntry.tenant_id == tenant_id,
            AdmissionWaitlistEntry.grade_level_code == grade_level_code,
        )
    ) or 0
    return int(count) + 1


def list_applications(db: Session, tenant_id: UUID) -> list[AdmissionApplication]:
    return list(
        db.scalars(
            select(AdmissionApplication)
            .where(AdmissionApplication.tenant_id == tenant_id)
            .order_by(AdmissionApplication.created_at.desc())
        )
    )


def list_waitlist(db: Session, tenant_id: UUID, grade_level_code: str) -> list[AdmissionWaitlistEntry]:
    return list(
        db.scalars(
            select(AdmissionWaitlistEntry)
            .where(
                AdmissionWaitlistEntry.tenant_id == tenant_id,
                AdmissionWaitlistEntry.grade_level_code == grade_level_code,
            )
            .order_by(AdmissionWaitlistEntry.position)
        )
    )
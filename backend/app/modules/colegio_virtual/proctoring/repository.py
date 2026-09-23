from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IntegrityFlagRecord, ProctoringConsentRecord


def save_consent(db: Session, *, tenant_id: UUID, student_id: UUID, guardian_user_id: UUID, scope: list[str], duration_minutes: int, viewer_role: str, verified_at: datetime) -> ProctoringConsentRecord:
    record = ProctoringConsentRecord(tenant_id=tenant_id, student_id=student_id, guardian_user_id=guardian_user_id, scope=json.dumps(scope), duration_minutes=duration_minutes, viewer_role=viewer_role, verified_at=verified_at)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def save_integrity_flag(db: Session, *, tenant_id: UUID, student_id: UUID, pattern: str, confidence: float, evidence: dict[str, object]) -> IntegrityFlagRecord:
    record = IntegrityFlagRecord(tenant_id=tenant_id, student_id=student_id, pattern=pattern, confidence=round(confidence * 100), evidence=json.dumps(evidence, sort_keys=True), notified_role="academic_coordinator", sanction_applied=False)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_flags(db: Session, *, tenant_id: UUID, student_id: UUID) -> list[IntegrityFlagRecord]:
    return list(db.scalars(select(IntegrityFlagRecord).where(IntegrityFlagRecord.tenant_id == tenant_id, IntegrityFlagRecord.student_id == student_id).order_by(IntegrityFlagRecord.created_at.desc())))
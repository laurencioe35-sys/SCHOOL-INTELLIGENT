from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CurriculumStandard, GradeLevel, Subject


def list_grade_levels(db: Session, tenant_id: UUID) -> list[GradeLevel]:
    return list(
        db.scalars(
            select(GradeLevel)
            .where(GradeLevel.tenant_id == tenant_id, GradeLevel.active.is_(True))
            .order_by(GradeLevel.sort_order)
        )
    )


def list_subjects(db: Session, tenant_id: UUID) -> list[Subject]:
    return list(
        db.scalars(
            select(Subject)
            .where(Subject.tenant_id == tenant_id, Subject.active.is_(True))
            .order_by(Subject.name)
        )
    )


def list_standards(db: Session, tenant_id: UUID) -> list[CurriculumStandard]:
    return list(
        db.scalars(
            select(CurriculumStandard)
            .where(CurriculumStandard.tenant_id == tenant_id, CurriculumStandard.active.is_(True))
            .order_by(CurriculumStandard.code)
        )
    )
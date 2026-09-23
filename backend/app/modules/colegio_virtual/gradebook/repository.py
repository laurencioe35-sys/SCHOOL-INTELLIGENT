from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assignment, Course, Enrollment, Grade


def create_assignment(
    db: Session, *, tenant_id: UUID, course_id: UUID, title: str, category: str, max_score: int
) -> Assignment:
    course = db.scalar(select(Course).where(Course.id == course_id, Course.tenant_id == tenant_id, Course.active.is_(True)))
    if course is None:
        raise ValueError("Course not found in tenant")
    if max_score <= 0:
        raise ValueError("max_score must be positive")
    assignment = Assignment(tenant_id=tenant_id, course_id=course_id, title=title.strip(), category=category.strip(), max_score=max_score)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


def record_grade(
    db: Session, *, tenant_id: UUID, assignment_id: UUID, student_id: UUID, score: int, comment: str | None = None
) -> Grade:
    assignment = db.scalar(select(Assignment).where(Assignment.id == assignment_id, Assignment.tenant_id == tenant_id, Assignment.active.is_(True)))
    enrollment = db.scalar(select(Enrollment).where(Enrollment.tenant_id == tenant_id, Enrollment.course_id == assignment.course_id if assignment else None, Enrollment.student_id == student_id, Enrollment.active.is_(True)))
    if assignment is None or enrollment is None:
        raise ValueError("Assignment or enrollment not found in tenant")
    if score < 0 or score > assignment.max_score:
        raise ValueError("Score outside assignment range")
    existing = db.scalar(select(Grade).where(Grade.tenant_id == tenant_id, Grade.student_id == student_id, Grade.course_id == assignment.course_id, Grade.comment == f"assignment:{assignment_id}"))
    if existing:
        existing.score = score
        db.commit()
        return existing
    grade = Grade(tenant_id=tenant_id, student_id=student_id, course_id=assignment.course_id, score=score, comment=f"assignment:{assignment_id}")
    db.add(grade)
    db.commit()
    db.refresh(grade)
    return grade
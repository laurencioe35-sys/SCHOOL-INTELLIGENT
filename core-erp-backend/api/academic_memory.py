"""Tenant-isolated, reusable academic memory; it is never a chat transcript store."""
import hashlib
import hmac
import os
import re

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.auth import get_current_user
from database.connection import get_db
from database.models import AcademicContent, AcademicContentType, Classroom, Role, User

router = APIRouter(prefix="/academic-memory", tags=["Memoria académica"])
_SECRET_PATTERN = re.compile(r"(password|api[_ -]?key|oauth|bearer\s+|cookie|secret|token)", re.I)


def _require_agent_service_key(x_agent_service_key: str = Header(default="")) -> None:
    configured = os.getenv("ACADEMIC_MEMORY_AGENT_SERVICE_KEY")
    if not configured or not x_agent_service_key or not hmac.compare_digest(configured, x_agent_service_key):
        raise HTTPException(status_code=403, detail="Internal agent authorization failed")


class AcademicContentRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=120)
    grade: str | None = Field(default=None, max_length=80)
    topic: str = Field(min_length=1, max_length=160)
    subtopic: str | None = Field(default=None, max_length=160)
    content_type: AcademicContentType
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=20000)
    steps: list[str] = Field(default_factory=list, max_length=100)
    answer: str | None = Field(default=None, max_length=10000)
    difficulty: str | None = Field(default=None, max_length=40)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    language: str = Field(default="en", min_length=2, max_length=12)
    classroom_id: str | None = None

    @field_validator("content", "title", "answer")
    @classmethod
    def reject_secrets(cls, value: str | None):
        if value and _SECRET_PATTERN.search(value):
            raise ValueError("Academic memory cannot contain credentials or authentication data")
        return value


def _classroom_in_user_org(db: Session, classroom_id: str | None, user: User) -> None:
    if classroom_id and not db.query(Classroom.id).filter(Classroom.id == classroom_id, Classroom.organization_id == user.organization_id).first():
        raise HTTPException(status_code=404, detail="Classroom not found")


@router.post("/contents", status_code=status.HTTP_201_CREATED)
def store_content(payload: AcademicContentRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role not in (Role.teacher, Role.admin):
        raise HTTPException(status_code=403, detail="Only teachers or administrators can store academic content")
    _classroom_in_user_org(db, payload.classroom_id, user)
    canonical = "\n".join((payload.subject.strip().lower(), payload.topic.strip().lower(), payload.content_type.value, payload.content.strip()))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    existing = db.query(AcademicContent).filter(AcademicContent.organization_id == user.organization_id, AcademicContent.content_hash == digest).first()
    if existing:
        return {"id": existing.id, "stored": False, "duplicate": True}
    record = AcademicContent(organization_id=user.organization_id, classroom_id=payload.classroom_id, created_by_user_id=user.id, content_hash=digest, **payload.model_dump())
    db.add(record)
    db.commit()
    return {"id": record.id, "stored": True, "duplicate": False}


@router.get("/contents")
def search_content(q: str = "", subject: str | None = None, grade: str | None = None, classroom_id: str | None = None, limit: int = 20, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _classroom_in_user_org(db, classroom_id, user)
    query = db.query(AcademicContent).filter(AcademicContent.organization_id == user.organization_id)
    if classroom_id: query = query.filter(or_(AcademicContent.classroom_id.is_(None), AcademicContent.classroom_id == classroom_id))
    if subject: query = query.filter(AcademicContent.subject.ilike(subject))
    if grade: query = query.filter(AcademicContent.grade == grade)
    if q.strip():
        phrase = f"%{q.strip()}%"
        query = query.filter(or_(AcademicContent.title.ilike(phrase), AcademicContent.topic.ilike(phrase), AcademicContent.content.ilike(phrase)))
    return query.order_by(AcademicContent.created_at.desc()).limit(min(max(limit, 1), 50)).all()


@router.get("/internal/retrieve", dependencies=[Depends(_require_agent_service_key)])
def retrieve_for_agent(organization_id: str, classroom_id: str, q: str, limit: int = 3, db: Session = Depends(get_db)):
    """Service-to-service retrieval. Tenant and classroom are verified here, never trusted from the worker."""
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id, Classroom.organization_id == organization_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")
    phrase = f"%{q.strip()}%"
    rows = db.query(AcademicContent).filter(
        AcademicContent.organization_id == organization_id,
        or_(AcademicContent.classroom_id.is_(None), AcademicContent.classroom_id == classroom_id),
        or_(AcademicContent.title.ilike(phrase), AcademicContent.topic.ilike(phrase), AcademicContent.content.ilike(phrase)),
    ).order_by(AcademicContent.created_at.desc()).limit(min(max(limit, 1), 10)).all()
    return [{"id": row.id, "subject": row.subject, "topic": row.topic, "content_type": row.content_type.value, "title": row.title, "content": row.content, "steps": row.steps, "answer": row.answer} for row in rows]

"""Tenant-scoped academic memory and its content gate."""
import hashlib
import json
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import AcademicContent, AcademicContentKeyword, AcademicKeyword

ALLOWED_TYPES = {"EXPLANATION", "DEFINITION", "FORMULA", "EXAMPLE", "EXERCISE", "SOLVED_EXERCISE", "QUIZ", "LESSON", "SUMMARY", "STUDY_GUIDE", "IMAGE", "DIAGRAM", "THREE_D_OBJECT_DESCRIPTION"}
SECRET_PATTERN = re.compile(r"(?i)(api[_ -]?key|password|oauth|access[_ -]?token|refresh[_ -]?token|cookie)\s*[:=]")

@dataclass(frozen=True)
class ValidatedContent:
    content_type: str; title: str; subject: str; topic: str; content: str
    grade: str | None; language: str; difficulty: str | None; steps: list[str]; answer: str | None; keywords: list[str]

def validate(payload: dict) -> ValidatedContent:
    if payload.get("academic") is not True:
        raise ValueError("Only academic content can be persisted")
    content_type = str(payload.get("content_type", "")).upper()
    if content_type not in ALLOWED_TYPES:
        raise ValueError("Unsupported academic content type")
    values = {key: str(payload.get(key, "")).strip() for key in ("title", "subject", "topic", "content")}
    if not all(values.values()):
        raise ValueError("Academic content requires title, subject, topic and content")
    if any(SECRET_PATTERN.search(value) for value in values.values()):
        raise ValueError("Secrets and authentication data cannot be academic content")
    steps = payload.get("steps", [])
    if not isinstance(steps, list) or not all(isinstance(step, str) and step.strip() for step in steps):
        raise ValueError("steps must be a list of non-empty strings")
    keywords = payload.get("keywords", [])
    if not isinstance(keywords, list): raise ValueError("keywords must be a list")
    return ValidatedContent(content_type, values["title"], values["subject"], values["topic"], values["content"], payload.get("grade"), str(payload.get("language") or "en"), payload.get("difficulty"), steps, payload.get("answer"), [str(k).strip().lower() for k in keywords if str(k).strip()][:20])

def fingerprint(item: ValidatedContent) -> str:
    canonical = "|".join((item.content_type, item.subject.lower(), item.topic.lower(), item.content.strip().lower()))
    return hashlib.sha256(canonical.encode()).hexdigest()

def store(db: Session, tenant_id: UUID, item: ValidatedContent, actor_id: UUID | None) -> tuple[AcademicContent, bool]:
    digest = fingerprint(item)
    existing = db.scalar(select(AcademicContent).where(AcademicContent.tenant_id == tenant_id, AcademicContent.content_hash == digest))
    if existing: return existing, False
    record = AcademicContent(tenant_id=tenant_id, created_by=actor_id, content_type=item.content_type, title=item.title, topic=item.topic, grade=item.grade, language=item.language, difficulty=item.difficulty, content=item.content, steps_json=json.dumps(item.steps), answer=item.answer, content_hash=digest)
    db.add(record); db.flush()
    for word in item.keywords:
        keyword = db.scalar(select(AcademicKeyword).where(AcademicKeyword.tenant_id == tenant_id, AcademicKeyword.value == word))
        if keyword is None:
            keyword = AcademicKeyword(tenant_id=tenant_id, value=word); db.add(keyword); db.flush()
        db.add(AcademicContentKeyword(content_id=record.id, keyword_id=keyword.id))
    return record, True

def search(db: Session, tenant_id: UUID, query: str, limit: int = 10) -> list[AcademicContent]:
    term = f"%{query.strip()}%"
    return list(db.scalars(select(AcademicContent).where(AcademicContent.tenant_id == tenant_id, or_(AcademicContent.title.ilike(term), AcademicContent.topic.ilike(term), AcademicContent.content.ilike(term))).order_by(AcademicContent.created_at.desc()).limit(limit)))

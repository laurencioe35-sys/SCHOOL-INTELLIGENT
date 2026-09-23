import json
import os
from uuid import UUID
import redis
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from .academic_memory import search, store, validate
from .core.audit import record_audit_event
from .db import get_db
from .dependencies import require_roles, tenant_context

router = APIRouter(prefix="/api/v1/academic-memory", tags=["academic-memory"])

class AcademicContentInput(BaseModel):
    academic: bool
    subject: str; grade: str | None = None; topic: str
    content_type: str; title: str; content: str
    steps: list[str] = Field(default_factory=list); answer: str | None = None
    difficulty: str | None = None; keywords: list[str] = Field(default_factory=list); language: str = "en"

def _event(name: str, tenant_id: UUID, content_id: str) -> None:
    url = os.getenv("REDIS_URL")
    if not url: return
    try: redis.from_url(url, decode_responses=True).xadd("academic:events", {"data": json.dumps({"type": name, "tenant_id": str(tenant_id), "content_id": content_id})})
    except redis.RedisError: return

@router.post("/contents", status_code=201)
def persist_content(payload: AcademicContentInput, claims: dict = Depends(require_roles("teacher", "admin")), tenant_id: UUID = Depends(tenant_context), db: Session = Depends(get_db)):
    try: item = validate(payload.model_dump())
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    content, created = store(db, tenant_id, item, UUID(claims["sub"])); db.commit()
    record_audit_event(db, tenant_id=tenant_id, actor_user_id=claims["sub"], entity_name="academic_content", entity_id=str(content.id), action="CREATE" if created else "DEDUPLICATED")
    db.commit(); _event("academic.content.stored" if created else "academic.content.deduplicated", tenant_id, str(content.id))
    return {"id": str(content.id), "created": created}

@router.get("/search")
def search_content(q: str = Query(min_length=2), tenant_id: UUID = Depends(tenant_context), db: Session = Depends(get_db)):
    records = search(db, tenant_id, q)
    return [{"id": str(item.id), "title": item.title, "topic": item.topic, "content_type": item.content_type, "content": item.content, "steps": json.loads(item.steps_json), "answer": item.answer} for item in records]

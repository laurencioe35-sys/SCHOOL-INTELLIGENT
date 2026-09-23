"""Authenticated bridge between immersive classrooms and the agent worker."""
import json
import os
import hmac

import redis
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import get_current_user
from database.connection import get_db
from database.models import BoardPublicationAudit, Classroom, Role, User

router = APIRouter(prefix="/agents", tags=["Agentes pedagógicos"])
INPUT_STREAM = os.getenv("AGENT_INPUT_STREAM", "class:transcript:chunks")
OUTPUT_STREAM = os.getenv("AGENT_OUTPUT_STREAM", "class:agent:results")
_redis = redis.from_url(os.getenv("ERP_REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)


class TranscriptRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=160)
    raw_text: str = Field(min_length=1, max_length=12_000)
    priority: str = Field(default="normal", pattern="^(urgent|high|normal|low)$")


class BoardPublicationRequest(BaseModel):
    classroom_id: str = Field(min_length=1, max_length=160)
    component_type: str = Field(pattern="^(object3d|formula|highlight)$")
    component_payload: dict = Field(min_length=1)


class CrdtAuthorizationRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=160)
    organization_id: str = Field(min_length=1, max_length=160)
    classroom_id: str = Field(min_length=1, max_length=160)


def _require_crdt_service_key(x_crdt_service_key: str = Header(default="")) -> None:
    configured = os.getenv("CRDT_AUTHORIZATION_SERVICE_KEY")
    if not configured or not x_crdt_service_key or not hmac.compare_digest(configured, x_crdt_service_key):
        raise HTTPException(status_code=403, detail="Internal CRDT authorization failed")


def _classroom_for_organization(db: Session, classroom_id: str, organization_id: str) -> None:
    exists = db.query(Classroom.id).filter(
        Classroom.id == classroom_id, Classroom.organization_id == organization_id
    ).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Aula no encontrada")


@router.post("/events/transcript", status_code=status.HTTP_202_ACCEPTED)
def publish_transcript(payload: TranscriptRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role not in (Role.teacher, Role.admin):
        raise HTTPException(status_code=403, detail="Solo docentes o administradores pueden usar los agentes")
    _classroom_for_organization(db, payload.session_id, user.organization_id)
    event = {
        "type": "transcript_chunk", "session_id": payload.session_id,
        "raw_text": payload.raw_text, "priority": payload.priority,
        "tenant_id": user.organization_id, "actor_user_id": user.id,
    }
    try:
        stream_id = _redis.xadd(INPUT_STREAM, {"data": json.dumps(event)})
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail="El transporte de agentes no está disponible") from exc
    return {"accepted": True, "stream_id": stream_id}


@router.post("/board-publications", status_code=status.HTTP_201_CREATED)
def audit_board_publication(payload: BoardPublicationRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role not in (Role.teacher, Role.admin):
        raise HTTPException(status_code=403, detail="Solo docentes o administradores pueden publicar en la pizarra")
    _classroom_for_organization(db, payload.classroom_id, user.organization_id)
    audit = BoardPublicationAudit(
        organization_id=user.organization_id,
        classroom_id=payload.classroom_id,
        actor_user_id=user.id,
        component_type=payload.component_type,
        component_payload=payload.component_payload,
    )
    db.add(audit)
    db.commit()
    return {"id": audit.id, "status": audit.status}


@router.post("/internal/crdt-authorize", dependencies=[Depends(_require_crdt_service_key)])
def authorize_crdt_connection(payload: CrdtAuthorizationRequest, db: Session = Depends(get_db)):
    """Authoritative tenant check for the CRDT service; not exposed to browsers."""
    user = db.query(User.id).filter(User.id == payload.user_id, User.organization_id == payload.organization_id).first()
    if not user:
        raise HTTPException(status_code=403, detail="User organization mismatch")
    _classroom_for_organization(db, payload.classroom_id, payload.organization_id)
    return {"authorized": True}


@router.get("/results")
def list_results(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _classroom_for_organization(db, session_id, user.organization_id)
    try:
        entries = _redis.xrevrange(OUTPUT_STREAM, count=50)
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail="El transporte de agentes no está disponible") from exc
    results = []
    for stream_id, fields in entries:
        try:
            data = json.loads(fields.get("data", ""))
        except json.JSONDecodeError:
            continue
        if data.get("session_id") == session_id and data.get("tenant_id") == user.organization_id:
            data["stream_id"] = stream_id
            results.append(data)
    return results

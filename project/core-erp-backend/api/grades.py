"""
Ingesta de notas.

Patrón real de alta escritura: la nota NO se escribe directamente en la
tabla `grades` en cada request. Se empuja a una lista en Redis (`grades:pending`)
y el `batch_db_worker.py` la consolida en lote. Esto evita que 40 alumnos
entregando examen al mismo tiempo generen 40 escrituras individuales a
Postgres compitiendo por locks.
"""
import hmac
import json
import os

import redis
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from database.connection import get_db
from database.models import User, Role, Classroom, Enrollment
from api.auth import get_current_user
from observability.logging_config import log_event
from sqlalchemy.orm import Session

router = APIRouter(prefix="/grades", tags=["Notas"])

REDIS_URL = os.getenv("ERP_REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

PENDING_QUEUE_KEY = "grades:pending"

# Secreto compartido con ai-agents-engine (ver config/erp_client.py de ese
# proyecto). No es un JWT de usuario porque el grading_agent no actúa en
# nombre de ningún profesor concreto — actúa como un servicio de confianza
# aparte. Sin esta variable configurada, el endpoint queda deshabilitado
# (fail-closed) para no aceptar "cualquier request sin auth" por accidente
# si alguien olvida configurarla en producción.
AI_AGENTS_INTERNAL_KEY = os.getenv("AI_AGENTS_INTERNAL_KEY", "")

# El grading_agent normaliza su calificación a 0.0-1.0 (ver
# ai-agents-engine/config/schemas.py:GradingResult). Este ERP registra
# notas en escala 0-20 (ver tests/test_erp.py, que usa `score: 18`), el
# estándar de calificación escolar en Perú — de ahí el factor de escala.
AI_GRADING_SCALE = 20.0


class GradeSubmit(BaseModel):
    student_id: str
    classroom_id: str
    score: float


class AgentGradeSubmit(BaseModel):
    """Payload que envía ai-agents-engine/config/erp_client.py después de
    que grading_agent califica una respuesta de alumno."""
    student_id: str
    classroom_id: str
    score_0_to_1: float = Field(ge=0.0, le=1.0)
    feedback: str
    needs_teacher_review: bool = False
    session_id: str | None = None


def _verify_internal_key(x_internal_service_key: str | None) -> None:
    if not AI_AGENTS_INTERNAL_KEY:
        raise HTTPException(
            status_code=503,
            detail="Integración con ai-agents-engine deshabilitada: falta configurar AI_AGENTS_INTERNAL_KEY",
        )
    if not x_internal_service_key or not hmac.compare_digest(x_internal_service_key, AI_AGENTS_INTERNAL_KEY):
        raise HTTPException(status_code=401, detail="Clave de servicio interna inválida")


@router.post("/submit", summary="Enviar una nota (va a buffer, no se consolida al instante)")
def submit_grade(payload: GradeSubmit, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role not in (Role.teacher, Role.admin):
        raise HTTPException(status_code=403, detail="Solo docentes pueden registrar notas")

    classroom = (
        db.query(Classroom)
        .filter(Classroom.id == payload.classroom_id, Classroom.organization_id == user.organization_id)
        .first()
    )
    if not classroom:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    # Antes de este check, cualquier student_id (incluso de otro colegio,
    # o inventado) pasaba el filtro de aula y solo se detectaba el error
    # más tarde en el batch worker (ver dead-letter queue). Validar aquí
    # la matrícula activa mueve el error al momento correcto: al ingresar
    # la nota, no minutos después al consolidarla.
    enrollment = (
        db.query(Enrollment)
        .filter(
            Enrollment.student_id == payload.student_id,
            Enrollment.classroom_id == payload.classroom_id,
            Enrollment.active.is_(True),
        )
        .first()
    )
    if not enrollment:
        raise HTTPException(status_code=400, detail="El alumno no está matriculado en esta aula")

    event = {
        "student_id": payload.student_id,
        "classroom_id": payload.classroom_id,
        "score": payload.score,
        "graded_by": "teacher",
    }
    redis_client.rpush(PENDING_QUEUE_KEY, json.dumps(event))
    return {"status": "buffered", "queue_length": redis_client.llen(PENDING_QUEUE_KEY)}


@router.post(
    "/submit-from-agent",
    summary="[Servicio interno] Ingesta de una nota generada por grading_agent (ai-agents-engine)",
)
def submit_grade_from_agent(
    payload: AgentGradeSubmit,
    db: Session = Depends(get_db),
    x_internal_service_key: str | None = Header(default=None),
):
    _verify_internal_key(x_internal_service_key)

    classroom = db.query(Classroom).filter(Classroom.id == payload.classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    enrollment = (
        db.query(Enrollment)
        .filter(
            Enrollment.student_id == payload.student_id,
            Enrollment.classroom_id == payload.classroom_id,
            Enrollment.active.is_(True),
        )
        .first()
    )
    if not enrollment:
        raise HTTPException(status_code=400, detail="El alumno no está matriculado en esta aula")

    event = {
        "student_id": payload.student_id,
        "classroom_id": payload.classroom_id,
        "score": round(payload.score_0_to_1 * AI_GRADING_SCALE, 2),
        "graded_by": "ai_grading_agent",
        "feedback": payload.feedback,
        "needs_teacher_review": payload.needs_teacher_review,
    }
    redis_client.rpush(PENDING_QUEUE_KEY, json.dumps(event))
    log_event(
        "grade_submitted_by_agent",
        student_id=payload.student_id,
        classroom_id=payload.classroom_id,
        needs_teacher_review=payload.needs_teacher_review,
        session_id=payload.session_id,
    )
    return {"status": "buffered", "queue_length": redis_client.llen(PENDING_QUEUE_KEY)}


@router.get("/queue/length", summary="Ver cuántas notas hay pendientes de consolidar")
def queue_length(user: User = Depends(get_current_user)):
    return {"pending": redis_client.llen(PENDING_QUEUE_KEY)}

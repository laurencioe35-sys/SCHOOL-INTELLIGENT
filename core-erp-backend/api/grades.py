"""
Ingesta de notas.

Patrón real de alta escritura: la nota NO se escribe directamente en la
tabla `grades` en cada request. Se empuja a una lista en Redis (`grades:pending`)
y el `batch_db_worker.py` la consolida en lote. Esto evita que 40 alumnos
entregando examen al mismo tiempo generen 40 escrituras individuales a
Postgres compitiendo por locks.
"""
import json
import os

import redis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database.connection import get_db
from database.models import User, Role, Classroom, Enrollment
from api.auth import get_current_user
from sqlalchemy.orm import Session

router = APIRouter(prefix="/grades", tags=["Notas"])

REDIS_URL = os.getenv("ERP_REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

PENDING_QUEUE_KEY = "grades:pending"


class GradeSubmit(BaseModel):
    student_id: str
    classroom_id: str
    score: float


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
    }
    redis_client.rpush(PENDING_QUEUE_KEY, json.dumps(event))
    return {"status": "buffered", "queue_length": redis_client.llen(PENDING_QUEUE_KEY)}


@router.get("/queue/length", summary="Ver cuántas notas hay pendientes de consolidar")
def queue_length(user: User = Depends(get_current_user)):
    return {"pending": redis_client.llen(PENDING_QUEUE_KEY)}

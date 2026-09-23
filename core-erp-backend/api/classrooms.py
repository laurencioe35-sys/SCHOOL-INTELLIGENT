from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from database.connection import get_db
from database.models import Classroom, ClassSession, User, Role
from api.auth import get_current_user

router = APIRouter(prefix="/classrooms", tags=["Aulas / Clases en vivo"])


class ClassroomCreate(BaseModel):
    name: str


class ClassroomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    teacher_id: str
    is_live: bool


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    classroom_id: str
    started_at: datetime


@router.post("", response_model=ClassroomOut)
def create_classroom(payload: ClassroomCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role not in (Role.teacher, Role.admin):
        raise HTTPException(status_code=403, detail="Solo docentes o administradores pueden crear aulas")
    classroom = Classroom(name=payload.name, teacher_id=user.id, organization_id=user.organization_id)
    db.add(classroom)
    db.commit()
    db.refresh(classroom)
    return classroom


def _get_classroom_in_org(db: Session, classroom_id: str, organization_id: str) -> Classroom:
    """Busca el aula filtrando SIEMPRE por organización — así un profesor
    del Colegio A no puede iniciar/terminar clases del Colegio B ni
    siquiera adivinando un UUID (habría que fuerza-bruta un UUID válido
    Y que además pertenezca a su organización, lo cual no es viable)."""
    classroom = (
        db.query(Classroom)
        .filter(Classroom.id == classroom_id, Classroom.organization_id == organization_id)
        .first()
    )
    if not classroom:
        raise HTTPException(status_code=404, detail="Aula no encontrada")
    return classroom


@router.post("/{classroom_id}/start", response_model=SessionOut, summary="Iniciar una clase en vivo")
def start_session(classroom_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    classroom = _get_classroom_in_org(db, classroom_id, user.organization_id)
    if classroom.teacher_id != user.id and user.role != Role.admin:
        raise HTTPException(status_code=403, detail="No eres el docente de esta aula")

    classroom.is_live = True
    session = ClassSession(classroom_id=classroom_id)
    db.add(session)
    db.commit()
    db.refresh(session)

    # NOTA DE ARQUITECTURA (no ejecutado aquí):
    # En producción, este endpoint dispararía una llamada al orquestador de
    # Media Pods (Kubernetes Job/Deployment efímero) para levantar el
    # contenedor de streaming aislado de esta sesión. Ver
    # multimedia-stream-server/README para el contrato de esa integración.
    return session


@router.post("/{classroom_id}/end", summary="Finalizar una clase en vivo")
def end_session(classroom_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    classroom = _get_classroom_in_org(db, classroom_id, user.organization_id)
    classroom.is_live = False
    session = (
        db.query(ClassSession)
        .filter(ClassSession.classroom_id == classroom_id, ClassSession.ended_at.is_(None))
        .order_by(ClassSession.started_at.desc())
        .first()
    )
    if session:
        session.ended_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ended"}


@router.get("", response_model=list[ClassroomOut])
def list_classrooms(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Filtrado por organización: esta es la línea que garantiza el
    # aislamiento multi-tenant en el listado — sin ella, cualquier usuario
    # vería las aulas de TODOS los colegios registrados en el sistema.
    return db.query(Classroom).filter(Classroom.organization_id == user.organization_id).all()

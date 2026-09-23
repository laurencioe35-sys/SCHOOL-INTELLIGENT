import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from database.connection import get_db
from database.models import Classroom, ClassSession, User, Role, Enrollment
from api.auth import get_current_user

router = APIRouter(prefix="/classrooms", tags=["Aulas / Clases en vivo"])

# Ver multimedia-stream-server/streaming/webrtc_handler.ts para el resto
# del contrato (flujo completo: este endpoint mintea el token -> el
# frontend se conecta a LiveKit con `livekit-client` usando ese token ->
# LiveKit manda webhooks al servidor de streaming).
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
LIVEKIT_WS_URL = os.getenv("LIVEKIT_WS_URL", "")
LIVEKIT_TOKEN_TTL_MINUTES = 180  # cubre una sesión de clase típica (~3h) sin sobre-extender el acceso


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
    livekit_ws_url: str | None = None
    livekit_token: str | None = None


class LiveKitTokenOut(BaseModel):
    ws_url: str
    token: str
    room_name: str
    identity: str
    can_publish: bool


def _mint_livekit_token(*, room_name: str, identity: str, can_publish: bool) -> str:
    """Mintea un access token de LiveKit real (JWT firmado con el SDK
    oficial `livekit-api`) — esto NO requiere red ni un servidor LiveKit
    corriendo: firmar el token es puramente criptografía local (HMAC),
    igual que ERP_SECRET_KEY en auth.py. Lo que sí requiere un servidor
    LiveKit real es que el CLIENTE luego use este token para conectarse
    (eso pasa en VideoMixer.tsx, fuera de este proceso).

    can_publish=True para el profesor (publica su cámara/pantalla);
    False para alumnos (solo se suscriben) — evita que cualquier alumno
    autenticado pueda transmitir su propio video sin que el profesor lo
    autorice explícitamente por otro medio.
    """
    if not (LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
        raise HTTPException(
            status_code=503,
            detail="Streaming de video deshabilitado: falta configurar LIVEKIT_API_KEY/LIVEKIT_API_SECRET",
        )
    from livekit import api as livekit_api

    grants = livekit_api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=can_publish,
        can_subscribe=True,
        can_publish_data=True,  # necesario para que el chat/reacciones también viajen por LiveKit si se usa
    )
    token = (
        livekit_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_ttl(timedelta(minutes=LIVEKIT_TOKEN_TTL_MINUTES))
        .with_grants(grants)
    )
    return token.to_jwt()


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


@router.post("", response_model=ClassroomOut)
def create_classroom(payload: ClassroomCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role not in (Role.teacher, Role.admin):
        raise HTTPException(status_code=403, detail="Solo docentes o administradores pueden crear aulas")
    classroom = Classroom(name=payload.name, teacher_id=user.id, organization_id=user.organization_id)
    db.add(classroom)
    db.commit()
    db.refresh(classroom)
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

    # NOTA DE ARQUITECTURA (Media Pods todavía no ejecutado aquí):
    # En producción, este endpoint también dispararía una llamada al
    # orquestador de Media Pods (Kubernetes Job/Deployment efímero, ver
    # deploy/k8s/README.md) para levantar el contenedor de streaming
    # aislado de esta sesión.
    #
    # El token de LiveKit sí es real (ver _mint_livekit_token): si
    # LIVEKIT_API_KEY/SECRET están configuradas, el profesor recibe aquí
    # mismo credenciales válidas para publicar en la sala
    # `classroom-{classroom_id}`. Sin esas variables (como en desarrollo
    # sin cuenta de LiveKit), livekit_ws_url/token quedan en None y el
    # frontend debe manejar esa ausencia (sesión sin video, solo
    # pizarra/CRDT) en vez de fallar.
    livekit_token = None
    if LIVEKIT_API_KEY and LIVEKIT_API_SECRET:
        livekit_token = _mint_livekit_token(
            room_name=f"classroom-{classroom_id}", identity=user.id, can_publish=True
        )

    return SessionOut(
        id=session.id,
        classroom_id=session.classroom_id,
        started_at=session.started_at,
        livekit_ws_url=LIVEKIT_WS_URL or None,
        livekit_token=livekit_token,
    )


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


@router.post(
    "/{classroom_id}/join-token",
    response_model=LiveKitTokenOut,
    summary="Obtener un token de LiveKit para unirse a una clase EN VIVO (alumno o docente)",
)
def join_session(classroom_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """A diferencia de /start (que solo el docente puede llamar y crea la
    sesión), este endpoint es para quien se UNE a una clase que ya está
    en vivo — típicamente un alumno, aunque un profesor reconectando
    también lo usaría. Por eso valida matrícula en vez de ser dueño del
    aula."""
    classroom = _get_classroom_in_org(db, classroom_id, user.organization_id)
    if not classroom.is_live:
        raise HTTPException(status_code=400, detail="Esta aula no tiene una clase en vivo en este momento")

    is_teacher_of_this_classroom = classroom.teacher_id == user.id
    is_enrolled = (
        db.query(Enrollment)
        .filter(Enrollment.student_id == user.id, Enrollment.classroom_id == classroom_id, Enrollment.active.is_(True))
        .first()
        is not None
    )
    if not (is_teacher_of_this_classroom or is_enrolled or user.role == Role.admin):
        raise HTTPException(status_code=403, detail="No perteneces a esta aula")

    # Solo el docente (o un admin) puede publicar video/audio; el resto
    # se suscribe. Esto se decide del lado del servidor (no confiamos en
    # que el cliente simplemente "no active la cámara" — el grant del
    # token es la única barrera real).
    can_publish = is_teacher_of_this_classroom or user.role == Role.admin
    token = _mint_livekit_token(
        room_name=f"classroom-{classroom_id}", identity=user.id, can_publish=can_publish
    )
    return LiveKitTokenOut(
        ws_url=LIVEKIT_WS_URL,
        token=token,
        room_name=f"classroom-{classroom_id}",
        identity=user.id,
        can_publish=can_publish,
    )

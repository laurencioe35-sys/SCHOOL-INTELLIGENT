"""
Compliance de datos de menores.

Un alumno de un ERP escolar es, en la gran mayoría de los casos, menor de
edad — esto no es un caso límite del sistema, es el caso normal. Este
módulo implementa las tres piezas mínimas que exige tratar datos de
menores con seriedad (no es asesoría legal; cada organización debe
confirmar los requisitos exactos con su asesor legal, pero esto cubre el
núcleo común entre normativas comparables como el Reglamento de la Ley
29733 en Perú, COPPA en EEUU y el "GDPR-K" en la UE):

  1. **Consentimiento del apoderado** antes de tratar datos de un menor
     (`POST /privacy/consent`, `GET /privacy/consent/{student_id}`), con
     historial completo (quién, cuándo, para qué tipo de tratamiento) —
     no solo un booleano que se sobreescribe.
  2. **Portabilidad de datos**: el alumno (o su apoderado a través de un
     docente/admin) puede pedir TODOS sus datos en un formato exportable
     (`GET /privacy/export/{student_id}`).
  3. **Derecho al olvido**, pero honesto sobre sus límites: se ANONIMIZA
     la información personal identificable (nombre, correo) en vez de
     borrar filas — las notas y facturas de un alumno no se pueden borrar
     sin más porque una institución educativa tiene obligaciones legales
     de retención de registros académicos y contables que compiten
     directamente con el derecho al olvido; este es exactamente el tipo
     de tensión real que un borrado ingenuo (`DELETE FROM users ...`)
     ignora y que aquí se resuelve explícitamente.

Cada acceso a datos de un alumno MENOR a través de este módulo queda
auditado en `DataAccessAuditLog` (ver database/models.py).
"""
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, ConfigDict

from database.connection import get_db
from database.models import (
    User, Role, Grade, GradeStatus, Enrollment, Invoice,
    ConsentRecord, ConsentType, DataAccessAuditLog, DataAccessAction,
    MINOR_AGE_THRESHOLD,
)
from api.auth import get_current_user, hash_password
from observability.logging_config import log_event

router = APIRouter(prefix="/privacy", tags=["Privacidad / Datos de menores"])


def _require_teacher_or_admin(user: User):
    if user.role not in (Role.teacher, Role.admin):
        raise HTTPException(status_code=403, detail="Solo docentes o administradores pueden gestionar consentimiento parental")


def _require_admin(user: User):
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Solo administradores pueden ejecutar esta acción sobre datos de menores")


def _get_student_in_org(db: Session, student_id: str, organization_id: str) -> User:
    student = (
        db.query(User)
        .filter(User.id == student_id, User.organization_id == organization_id, User.role == Role.student)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado en esta organización")
    return student


def _audit(db: Session, actor: User, student_id: str, action: DataAccessAction):
    db.add(DataAccessAuditLog(actor_user_id=actor.id, subject_student_id=student_id, action=action))


def active_consent(db: Session, student_id: str, consent_type: ConsentType) -> ConsentRecord | None:
    """El consentimiento vigente es el registro más reciente sin revocar
    para ese tipo — una revocación nueva SIEMPRE gana sobre un
    otorgamiento anterior, incluso si alguien vuelve a otorgar consentimiento
    después hay que crear un registro nuevo (nunca se "reactiva" uno viejo,
    para no perder el rastro de que hubo una revocación en el medio)."""
    return (
        db.query(ConsentRecord)
        .filter(
            ConsentRecord.student_id == student_id,
            ConsentRecord.consent_type == consent_type,
            ConsentRecord.revoked_at.is_(None),
        )
        .order_by(ConsentRecord.granted_at.desc())
        .first()
    )


# --- Consentimiento parental --------------------------------------------

class GrantConsentRequest(BaseModel):
    student_id: str
    guardian_full_name: str
    guardian_email: EmailStr
    consent_type: ConsentType = ConsentType.data_processing


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    consent_type: ConsentType
    guardian_full_name: str
    guardian_email: str
    granted_at: datetime
    revoked_at: datetime | None


@router.post("/consent", response_model=ConsentOut, summary="Registrar consentimiento del apoderado")
def grant_consent(payload: GrantConsentRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_teacher_or_admin(user)
    student = _get_student_in_org(db, payload.student_id, user.organization_id)

    record = ConsentRecord(
        student_id=student.id,
        consent_type=payload.consent_type,
        guardian_full_name=payload.guardian_full_name,
        guardian_email=payload.guardian_email,
        granted_by_user_id=user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    log_event("parental_consent_granted", student_id=student.id, consent_type=payload.consent_type.value,
               granted_by=user.id)
    return record


@router.delete("/consent/{consent_id}", summary="Revocar un consentimiento otorgado")
def revoke_consent(consent_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_teacher_or_admin(user)
    record = (
        db.query(ConsentRecord)
        .join(User, ConsentRecord.student_id == User.id)
        .filter(ConsentRecord.id == consent_id, User.organization_id == user.organization_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Registro de consentimiento no encontrado")
    if record.revoked_at is not None:
        raise HTTPException(status_code=400, detail="Este consentimiento ya estaba revocado")
    record.revoked_at = datetime.now(timezone.utc)
    db.commit()
    log_event("parental_consent_revoked", consent_id=consent_id, student_id=record.student_id, revoked_by=user.id)
    return {"status": "revoked"}


class ConsentStatusOut(BaseModel):
    student_id: str
    is_minor: bool | None
    consents: dict[str, ConsentOut | None]


@router.get("/consent/{student_id}", response_model=ConsentStatusOut, summary="Estado de consentimiento de un alumno")
def get_consent_status(student_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role == Role.student and user.id != student_id:
        raise HTTPException(status_code=403, detail="No puedes ver el consentimiento de otro alumno")
    student = _get_student_in_org(db, student_id, user.organization_id)

    return ConsentStatusOut(
        student_id=student.id,
        is_minor=student.is_minor(),
        consents={
            ct.value: active_consent(db, student.id, ct)
            for ct in ConsentType
        },
    )


# --- Portabilidad de datos (export) --------------------------------------

class DataExportOut(BaseModel):
    student: dict
    enrollments: list[dict]
    grades: list[dict]
    invoices: list[dict]
    consent_history: list[dict]
    exported_at: datetime


@router.get("/export/{student_id}", response_model=DataExportOut, summary="Exportar todos los datos de un alumno")
def export_student_data(student_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Portabilidad de datos: devuelve TODO lo que el sistema tiene sobre
    un alumno en un solo documento estructurado. Accesible por el propio
    alumno, o por docente/admin de su organización (para atender un
    pedido del apoderado, que hoy no tiene cuenta propia en el sistema —
    ver README, "rol de apoderado" sigue siendo un pendiente aparte)."""
    if user.role == Role.student and user.id != student_id:
        raise HTTPException(status_code=403, detail="No puedes exportar los datos de otro alumno")
    student = _get_student_in_org(db, student_id, user.organization_id)

    enrollments = db.query(Enrollment).filter(Enrollment.student_id == student.id).all()
    grades = db.query(Grade).filter(Grade.student_id == student.id).all()
    invoices = db.query(Invoice).filter(Invoice.student_id == student.id).all()
    consents = db.query(ConsentRecord).filter(ConsentRecord.student_id == student.id).all()

    if student.is_minor():
        _audit(db, user, student.id, DataAccessAction.export_data)

    db.commit()
    log_event("student_data_exported", student_id=student.id, exported_by=user.id)

    return DataExportOut(
        student={
            "id": student.id, "full_name": student.full_name, "email": student.email,
            "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else None,
            "guardian_email": student.guardian_email,
        },
        enrollments=[{"classroom_id": e.classroom_id, "active": e.active, "enrolled_at": e.enrolled_at.isoformat()} for e in enrollments],
        grades=[{"classroom_id": g.classroom_id, "score": g.score, "status": g.status.value, "created_at": g.created_at.isoformat()} for g in grades],
        invoices=[{"concept": i.concept, "amount_cents": i.amount_cents, "status": i.status.value, "due_date": i.due_date.isoformat()} for i in invoices],
        consent_history=[{"consent_type": c.consent_type.value, "granted_at": c.granted_at.isoformat(),
                           "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None} for c in consents],
        exported_at=datetime.now(timezone.utc),
    )


# --- Derecho al olvido (anonimización) -----------------------------------

_ANONYMIZED_MARKER = "Alumno Eliminado"


@router.delete("/data/{student_id}", summary="Anonimizar los datos personales de un alumno (derecho al olvido)")
def erase_student_data(student_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Anonimiza — NO borra filas de notas/facturas/matrículas, que se
    conservan por obligación de retención de registros académicos y
    contables, pero ya sin ningún dato personal identificable adjunto más
    allá del ID interno. Solo admin: es una operación irreversible sobre
    datos de un alumno real, no algo que un docente deba poder ejecutar
    solo."""
    _require_admin(user)
    student = _get_student_in_org(db, student_id, user.organization_id)

    student.full_name = _ANONYMIZED_MARKER
    student.email = f"eliminado+{student.id}@anonimizado.local"
    student.hashed_password = hash_password(uuid.uuid4().hex)  # contraseña aleatoria irrecuperable: invalida cualquier login futuro
    student.date_of_birth = None
    student.guardian_email = None

    _audit(db, user, student.id, DataAccessAction.erase_data)
    db.commit()
    log_event("student_data_erased", student_id=student.id, erased_by=user.id)
    return {"status": "anonymized", "student_id": student.id}

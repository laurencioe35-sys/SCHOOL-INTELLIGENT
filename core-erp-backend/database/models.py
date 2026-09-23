"""
Modelos de datos del ERP educativo.

Multi-tenancy: cada User y cada Classroom pertenecen a una Organization
(un colegio/institución). Grade y ClassSession NO tienen organization_id
propio a propósito — se derivan siempre de su Classroom, para evitar que
existan dos fuentes de verdad que puedan desincronizarse (una nota nunca
podría pertenecer a una organización distinta a la de su aula). Todas las
queries de la capa API deben filtrar por organization_id del usuario
autenticado (ver api/classrooms.py y api/grades.py).
"""
import uuid
from datetime import datetime, timezone, date

from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Float, Enum, Boolean, Text, JSON, Index, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base
import enum

Base = declarative_base()

# Compliance de datos de menores: edad bajo la cual se exige
# consentimiento del padre/apoderado para procesar datos del alumno.
# Configurable porque distintas jurisdicciones fijan umbrales distintos
# para el consentimiento de datos de menores (GDPR/GDPR-K usa 16, COPPA
# en EEUU usa 13); el valor por defecto (14) sigue el criterio del
# Reglamento de la Ley N° 29733 de Protección de Datos Personales del
# Perú, que exige autorización del representante legal para el
# tratamiento de datos de menores de 14 años. Esto NO es asesoría legal:
# cada organización debe confirmar el umbral aplicable con su asesor legal.
import os as _os
MINOR_AGE_THRESHOLD = int(_os.getenv("PRIVACY_MINOR_AGE_THRESHOLD", "14"))


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow():
    return datetime.now(timezone.utc)


class Organization(Base):
    """Un colegio/institución. Es el límite de aislamiento de datos:
    ningún usuario de una organización debe poder ver aulas, alumnos o
    notas de otra."""
    __tablename__ = "organizations"
    id = Column(String, primary_key=True, default=new_id)
    name = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=utcnow)


class Role(str, enum.Enum):
    student = "student"
    teacher = "teacher"
    admin = "admin"


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=new_id)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(Role), nullable=False, default=Role.student)
    created_at = Column(DateTime, default=utcnow)

    # Compliance de datos de menores (nuevo): date_of_birth es nullable
    # porque los usuarios que ya existían antes de esta migración no lo
    # tienen — is_minor() los trata como "desconocido" (ni menor ni
    # confirmado adulto) hasta que se complete el dato, en vez de asumir
    # ninguno de los dos casos por defecto. guardian_email es el contacto
    # del padre/apoderado, usado para registrar y notificar consentimiento.
    date_of_birth = Column(Date, nullable=True)
    guardian_email = Column(String, nullable=True)

    organization = relationship("Organization")

    def is_minor(self, reference_date: date | None = None) -> bool | None:
        """True/False si se conoce la fecha de nacimiento, None si no se
        conoce (no se debe asumir "no es menor" ante falta de dato — eso
        sería exactamente el tipo de suposición insegura que este módulo
        de compliance existe para evitar)."""
        if self.date_of_birth is None:
            return None
        today = reference_date or datetime.now(timezone.utc).date()
        age = today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )
        return age < MINOR_AGE_THRESHOLD


class Classroom(Base):
    __tablename__ = "classrooms"
    id = Column(String, primary_key=True, default=new_id)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    name = Column(String, nullable=False)
    teacher_id = Column(String, ForeignKey("users.id"), nullable=False)
    is_live = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    organization = relationship("Organization")
    teacher = relationship("User")
    sessions = relationship("ClassSession", back_populates="classroom")


class ClassSession(Base):
    """Una sesión de clase en vivo (inicio/fin), unidad sobre la que
    cuelgan eventos de la pizarra 3D y las notas generadas por IA."""
    __tablename__ = "class_sessions"
    id = Column(String, primary_key=True, default=new_id)
    classroom_id = Column(String, ForeignKey("classrooms.id"), nullable=False)
    started_at = Column(DateTime, default=utcnow)
    ended_at = Column(DateTime, nullable=True)

    classroom = relationship("Classroom", back_populates="sessions")


class GradeStatus(str, enum.Enum):
    pending = "pending"     # llegó al buffer (Redis en producción) pero no se consolidó
    committed = "committed"  # ya se guardó en la tabla definitiva por el batch worker


class Grade(Base):
    """Nota de un alumno. El campo `status` refleja el patrón real de
    ingestión: llega en caliente (pending) y el batch worker la consolida
    (committed) para no golpear la base de datos con escrituras 1 a 1."""
    __tablename__ = "grades"
    id = Column(String, primary_key=True, default=new_id)
    student_id = Column(String, ForeignKey("users.id"), nullable=False)
    classroom_id = Column(String, ForeignKey("classrooms.id"), nullable=False)
    score = Column(Float, nullable=False)
    status = Column(Enum(GradeStatus), default=GradeStatus.pending)
    created_at = Column(DateTime, default=utcnow)
    committed_at = Column(DateTime, nullable=True)


class Enrollment(Base):
    """Matrícula: relación explícita alumno-aula. Sin esta tabla, un aula
    solo tenía un `teacher_id` pero ningún alumno formalmente matriculado
    — cualquier student_id se podía usar en /grades/submit sin verificar
    que el alumno realmente pertenezca a esa aula."""
    __tablename__ = "enrollments"
    id = Column(String, primary_key=True, default=new_id)
    student_id = Column(String, ForeignKey("users.id"), nullable=False)
    classroom_id = Column(String, ForeignKey("classrooms.id"), nullable=False)
    enrolled_at = Column(DateTime, default=utcnow)
    active = Column(Boolean, default=True)

    student = relationship("User")
    classroom = relationship("Classroom")


class InvoiceStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    overdue = "overdue"
    cancelled = "cancelled"


class Invoice(Base):
    """Pensión/cobro de un alumno. Diseñado para integrarse con una
    pasarela de pago real (Culqi/Niubiz/MercadoPago son las más comunes
    en Perú) — ver api/billing.py para el punto exacto de integración."""
    __tablename__ = "invoices"
    id = Column(String, primary_key=True, default=new_id)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    student_id = Column(String, ForeignKey("users.id"), nullable=False)
    concept = Column(String, nullable=False)  # ej. "Pensión Julio 2026"
    amount_cents = Column(Float, nullable=False)  # en céntimos, para evitar errores de redondeo con floats
    currency = Column(String, default="PEN")
    status = Column(Enum(InvoiceStatus), default=InvoiceStatus.pending)
    due_date = Column(DateTime, nullable=False)
    paid_at = Column(DateTime, nullable=True)
    payment_reference = Column(String, nullable=True)  # ID de transacción de la pasarela real
    created_at = Column(DateTime, default=utcnow)

    student = relationship("User")
    organization = relationship("Organization")


class ConsentType(str, enum.Enum):
    data_processing = "data_processing"  # tratamiento básico de datos (obligatorio para usar el ERP)
    media_recording = "media_recording"  # grabación/registro de la clase en vivo (voz/video/pizarra)
    marketing = "marketing"              # comunicaciones no esenciales (boletines, promociones)


class ConsentRecord(Base):
    """Consentimiento del padre/apoderado para el tratamiento de datos de
    un alumno menor de edad (ver User.is_minor / MINOR_AGE_THRESHOLD).

    Se guarda un registro NUEVO por cada otorgamiento/revocación en vez de
    sobreescribir un único campo boolean en User — es lo que permite
    responder "¿cuándo y quién autorizó esto?" ante una auditoría, no solo
    "¿está autorizado ahora mismo?". `active_consent()` en api/privacy.py
    es quien resuelve el estado vigente a partir de este historial.
    """
    __tablename__ = "consent_records"
    id = Column(String, primary_key=True, default=new_id)
    student_id = Column(String, ForeignKey("users.id"), nullable=False)
    consent_type = Column(Enum(ConsentType), nullable=False, default=ConsentType.data_processing)
    guardian_full_name = Column(String, nullable=False)
    guardian_email = Column(String, nullable=False)
    granted_by_user_id = Column(String, ForeignKey("users.id"), nullable=False)  # quién lo registró en el sistema (docente/admin)
    granted_at = Column(DateTime, default=utcnow)
    revoked_at = Column(DateTime, nullable=True)

    student = relationship("User", foreign_keys=[student_id])
    granted_by = relationship("User", foreign_keys=[granted_by_user_id])


class DataAccessAction(str, enum.Enum):
    view_profile = "view_profile"
    export_data = "export_data"
    erase_data = "erase_data"


class DataAccessAuditLog(Base):
    """Rastro de auditoría de accesos a datos de menores — quién vio o
    exportó o borró los datos de qué alumno y cuándo. Requerido por el
    principio de "responsabilidad proactiva" (accountability) de la
    normativa de protección de datos: no basta con proteger los datos,
    hay que poder DEMOSTRAR quién accedió a ellos ante un reclamo o una
    fiscalización. Se escribe SOLO para accesos a datos de alumnos
    menores de edad (ver api/privacy.py) — auditar cada GET de cada
    usuario sería ruido, no señal.
    """
    __tablename__ = "data_access_audit_log"
    id = Column(String, primary_key=True, default=new_id)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    subject_student_id = Column(String, ForeignKey("users.id"), nullable=False)
    action = Column(Enum(DataAccessAction), nullable=False)
    created_at = Column(DateTime, default=utcnow)

    actor = relationship("User", foreign_keys=[actor_user_id])
    subject = relationship("User", foreign_keys=[subject_student_id])


class AcademicContentType(str, enum.Enum):
    explanation = "EXPLANATION"
    definition = "DEFINITION"
    formula = "FORMULA"
    example = "EXAMPLE"
    exercise = "EXERCISE"
    solved_exercise = "SOLVED_EXERCISE"
    quiz = "QUIZ"
    lesson = "LESSON"
    summary = "SUMMARY"
    study_guide = "STUDY_GUIDE"
    diagram = "DIAGRAM"
    three_d_object_description = "THREE_D_OBJECT_DESCRIPTION"


class AcademicContent(Base):
    """Reusable academic memory. It is deliberately separate from chat/events."""
    __tablename__ = "academic_contents"
    __table_args__ = (
        UniqueConstraint("organization_id", "content_hash", name="uq_academic_content_org_hash"),
        Index("ix_academic_content_org_search", "organization_id", "subject", "grade", "topic"),
    )
    id = Column(String, primary_key=True, default=new_id)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    classroom_id = Column(String, ForeignKey("classrooms.id"), nullable=True, index=True)
    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    subject = Column(String, nullable=False)
    grade = Column(String, nullable=True)
    topic = Column(String, nullable=False)
    subtopic = Column(String, nullable=True)
    content_type = Column(Enum(AcademicContentType), nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    steps = Column(JSON, nullable=False, default=list)
    answer = Column(Text, nullable=True)
    difficulty = Column(String, nullable=True)
    keywords = Column(JSON, nullable=False, default=list)
    language = Column(String, nullable=False, default="en")
    content_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utcnow)


class BoardPublicationAudit(Base):
    __tablename__ = "board_publication_audit"
    id = Column(String, primary_key=True, default=new_id)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    classroom_id = Column(String, ForeignKey("classrooms.id"), nullable=False, index=True)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    component_type = Column(String, nullable=False)
    component_payload = Column(JSON, nullable=False)
    status = Column(String, nullable=False, default="approved")
    created_at = Column(DateTime, default=utcnow)

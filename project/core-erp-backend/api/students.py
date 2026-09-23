"""
Gestión de estudiantes: matrícula (enrollment) y perfil detallado.

Antes de este módulo, un "alumno" era solo un User con role=student, sin
ninguna relación formal con un aula — cualquier student_id se podía pasar
a /grades/submit sin verificar que el alumno estuviera realmente
matriculado en esa aula. Este módulo cierra ese hueco.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from database.connection import get_db
from database.models import User, Role, Classroom, Enrollment, Grade, GradeStatus, ConsentType
from api.auth import get_current_user
from api.privacy import active_consent
from observability.logging_config import log_event

router = APIRouter(prefix="/students", tags=["Estudiantes / Matrícula"])


class EnrollRequest(BaseModel):
    student_id: str
    classroom_id: str


class EnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    classroom_id: str
    enrolled_at: datetime
    active: bool


class StudentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    email: str


class GradeHistoryItem(BaseModel):
    classroom_id: str
    classroom_name: str
    score: float
    status: str
    created_at: datetime


class StudentProfile(BaseModel):
    student: StudentSummary
    classrooms: list[str]
    grade_history: list[GradeHistoryItem]
    average_score: float | None


def _require_teacher_or_admin(user: User):
    if user.role not in (Role.teacher, Role.admin):
        raise HTTPException(status_code=403, detail="Solo docentes o administradores pueden gestionar matrículas")


@router.post("/enroll", response_model=EnrollmentOut, summary="Matricular a un alumno en un aula")
def enroll_student(payload: EnrollRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_teacher_or_admin(user)

    classroom = (
        db.query(Classroom)
        .filter(Classroom.id == payload.classroom_id, Classroom.organization_id == user.organization_id)
        .first()
    )
    if not classroom:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    student = (
        db.query(User)
        .filter(User.id == payload.student_id, User.organization_id == user.organization_id, User.role == Role.student)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado en esta organización")

    existing = (
        db.query(Enrollment)
        .filter(Enrollment.student_id == student.id, Enrollment.classroom_id == classroom.id, Enrollment.active.is_(True))
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="El alumno ya está matriculado en esta aula")

    # Compliance de datos de menores (nuevo): si se conoce la fecha de
    # nacimiento y el alumno es menor (User.is_minor()), no se puede
    # matricular — lo que dispara todo el flujo de tratamiento de datos
    # (notas, asistencia a clases en vivo, facturación) — sin
    # consentimiento parental activo ya registrado vía
    # POST /privacy/consent. Si is_minor() es None (no se conoce la
    # fecha de nacimiento) se deja pasar a propósito: bloquear por un
    # dato que ni siquiera se pidió en el registro original de alumnos
    # que ya existían antes de esta migración sería retroactivo e injusto;
    # el hueco de "no sabemos si es menor" se cierra pidiendo el dato en
    # el registro, no penalizando aquí a alumnos ya existentes.
    if student.is_minor() is True:
        consent = active_consent(db, student.id, ConsentType.data_processing)
        if consent is None:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Este alumno es menor de edad y no tiene consentimiento parental "
                    "activo para tratamiento de datos. Regístralo primero con "
                    "POST /privacy/consent."
                ),
            )

    enrollment = Enrollment(student_id=student.id, classroom_id=classroom.id)
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    log_event("student_enrolled", student_id=student.id, classroom_id=classroom.id)
    return enrollment


@router.delete("/enroll/{enrollment_id}", summary="Dar de baja una matrícula")
def unenroll_student(enrollment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_teacher_or_admin(user)
    enrollment = db.query(Enrollment).join(Classroom).filter(
        Enrollment.id == enrollment_id, Classroom.organization_id == user.organization_id
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Matrícula no encontrada")
    enrollment.active = False
    db.commit()
    log_event("student_unenrolled", enrollment_id=enrollment_id)
    return {"status": "unenrolled"}


@router.get("", response_model=list[StudentSummary], summary="Listar alumnos de la organización")
def list_students(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_teacher_or_admin(user)
    return db.query(User).filter(User.organization_id == user.organization_id, User.role == Role.student).all()


@router.get("/{student_id}/profile", response_model=StudentProfile, summary="Perfil detallado del alumno")
def student_profile(student_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Un alumno puede ver su propio perfil; docentes/admin pueden ver
    # cualquier perfil de su organización.
    if user.role == Role.student and user.id != student_id:
        raise HTTPException(status_code=403, detail="No puedes ver el perfil de otro alumno")

    student = (
        db.query(User)
        .filter(User.id == student_id, User.organization_id == user.organization_id)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    enrollments = (
        db.query(Enrollment)
        .filter(Enrollment.student_id == student_id, Enrollment.active.is_(True))
        .all()
    )
    classroom_ids = [e.classroom_id for e in enrollments]

    grades = (
        db.query(Grade)
        .filter(Grade.student_id == student_id, Grade.status == GradeStatus.committed)
        .all()
    )
    classrooms_by_id = {
        c.id: c.name for c in db.query(Classroom).filter(Classroom.id.in_([g.classroom_id for g in grades])).all()
    } if grades else {}

    grade_history = [
        GradeHistoryItem(
            classroom_id=g.classroom_id,
            classroom_name=classrooms_by_id.get(g.classroom_id, "Aula desconocida"),
            score=g.score,
            status=g.status.value,
            created_at=g.created_at,
        )
        for g in grades
    ]
    average = round(sum(g.score for g in grades) / len(grades), 2) if grades else None

    return StudentProfile(
        student=student,
        classrooms=classroom_ids,
        grade_history=grade_history,
        average_score=average,
    )

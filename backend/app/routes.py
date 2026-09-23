from datetime import UTC, datetime
from uuid import UUID, uuid4
import json
import jwt

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from base64 import b64encode
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .core.audit import record_audit_event
from .modules.whiteboard.collaboration.repository import append_operation, list_operations
from .config import get_settings
from .db import SessionLocal, get_db
from .dependencies import require_roles, tenant_context
from .models import (
    AdmissionApplication,
    AdmissionWaitlistEntry,
    Attendance,
    Course,
    CurriculumStandard,
    Enrollment,
    Grade,
    GradeLevel,
    GuardianStudent,
    Invoice,
    InvoiceStatus,
    Student,
    Subject,
    Subscription,
    Tenant,
    TeacherCourse,
    User,
)
from .security import create_access_token, current_claims, verify_password
from .schemas import (
    AdmissionApplicationCreate,
    AdmissionApplicationRead,
    AttendanceCreate,
    AttendanceRead,
    CourseCreate,
    CourseRead,
    CurriculumStandardCreate,
    CurriculumStandardRead,
    EnrollmentCreate,
    EnrollmentRead,
    GradeCreate,
    GradeLevelCreate,
    GradeLevelRead,
    GradeRead,
    InvoiceCreate,
    InvoiceRead,
    LoginRequest,
    LoginResponse,
    PayInvoiceRequest,
    StudentCreate,
    StudentRead,
    SubjectCreate,
    SubjectRead,
    PlatformSubscriptionUpdate,
    TranscriptChunkCreate,
    WhiteboardOperationCreate,
)
from .modules.colegio_virtual.admissions.eligibility_check import check_age_eligibility
from .modules.colegio_virtual.admissions.enrollment_service import decide_enrollment
from .modules.colegio_virtual.admissions.application_intake import AdmissionApplication as DomainApplication
from .modules.colegio_virtual.admissions.waitlist_manager import WaitlistManager
from .modules.colegio_virtual.curriculum.repository import (
    list_grade_levels as repository_list_grade_levels,
    list_standards as repository_list_standards,
    list_subjects as repository_list_subjects,
)
from .modules.colegio_virtual.admissions.repository import (
    list_applications as repository_list_applications,
    next_waitlist_position,
)

router = APIRouter(prefix="/api/v1")

_admission_waitlists = WaitlistManager()


class WhiteboardRoomHub:
    def __init__(self):
        self.rooms: dict[str, set[WebSocket]] = {}

    async def join(self, room_key: str, socket: WebSocket) -> None:
        await socket.accept()
        self.rooms.setdefault(room_key, set()).add(socket)

    def leave(self, room_key: str, socket: WebSocket) -> None:
        clients = self.rooms.get(room_key)
        if clients is None:
            return
        clients.discard(socket)
        if not clients:
            self.rooms.pop(room_key, None)

    async def broadcast(self, room_key: str, message: dict, sender: WebSocket) -> None:
        clients = tuple(self.rooms.get(room_key, set()))
        for client in clients:
            if client is sender:
                continue
            try:
                await client.send_json(message)
            except Exception:
                self.leave(room_key, client)


_whiteboard_hub = WhiteboardRoomHub()


def _require_platform_admin(claims: dict) -> None:
    if claims.get("role") != "platform_admin":
        raise HTTPException(status_code=403, detail="Platform administrator access required")


@router.get("/platform/subscriptions")
def list_platform_subscriptions(claims: dict = Depends(current_claims), db: Session = Depends(get_db)):
    _require_platform_admin(claims)
    rows = db.execute(select(Subscription, Tenant).join(Tenant, Tenant.id == Subscription.tenant_id)).all()
    return [
        {"id": str(subscription.id), "tenant_id": str(tenant.id), "workspace_name": tenant.name,
         "plan": subscription.plan_code, "status": subscription.status, "provider": subscription.provider,
         "current_period_end": subscription.current_period_end}
        for subscription, tenant in rows
    ]


@router.patch("/platform/subscriptions/{subscription_id}")
def update_platform_subscription(subscription_id: UUID, payload: PlatformSubscriptionUpdate, claims: dict = Depends(current_claims), db: Session = Depends(get_db)):
    _require_platform_admin(claims)
    subscription = db.get(Subscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    plan = (payload.plan or subscription.plan_code).upper()
    status_value = (payload.status or subscription.status).lower()
    if plan not in {"TRIAL", "BASICO", "PLUS", "PRO", "MAESTRO", "CONTA_PRO"} or status_value not in {"trialing", "active", "past_due", "canceled"}:
        raise HTTPException(status_code=422, detail="Plan or status not supported")
    subscription.plan_code = plan
    subscription.status = status_value
    db.commit()
    return {"id": str(subscription.id), "plan": plan, "status": status_value}


@router.get("/whiteboard/{room_id}/operations")
def get_whiteboard_operations(
    room_id: str,
    tenant_id: UUID = Depends(tenant_context),
    db: Session = Depends(get_db),
):
    operations = list_operations(db, tenant_id=tenant_id, room_id=room_id)
    return [
        {
            "operation_id": operation.operation_id,
            "actor_id": operation.actor_id,
            "operation_type": operation.operation_type,
            "payload": json.loads(operation.payload),
            "created_at": operation.created_at.isoformat(),
        }
        for operation in operations
    ]


@router.post("/whiteboard/{room_id}/operations", status_code=201)
def post_whiteboard_operation(
    room_id: str,
    payload: WhiteboardOperationCreate,
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    operation = append_operation(
        db,
        tenant_id=tenant_id,
        room_id=room_id,
        operation_id=payload.operation_id,
        actor_id=str(claims["sub"]),
        operation_type=payload.operation_type,
        payload=payload.payload,
    )
    return {
        "operation_id": operation.operation_id,
        "actor_id": operation.actor_id,
        "operation_type": operation.operation_type,
        "payload": json.loads(operation.payload),
        "created_at": operation.created_at.isoformat(),
    }


@router.websocket("/whiteboard/{room_id}/stream")
async def whiteboard_stream(room_id: str, websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        claims = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
        tenant_id = UUID(str(claims["tenant_id"]))
        actor_id = str(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        await websocket.close(code=4401)
        return

    room_key = f"{tenant_id}:{room_id}"
    await _whiteboard_hub.join(room_key, websocket)
    try:
        with SessionLocal() as db:
            snapshot = list_operations(db, tenant_id=tenant_id, room_id=room_id)
        await websocket.send_json({
            "type": "snapshot",
            "room_id": room_id,
            "operations": [
                {
                    "operation_id": operation.operation_id,
                    "actor_id": operation.actor_id,
                    "operation_type": operation.operation_type,
                    "payload": json.loads(operation.payload),
                    "created_at": operation.created_at.isoformat(),
                }
                for operation in snapshot
            ],
        })
        while True:
            message = await websocket.receive_json()
            operation_payload = WhiteboardOperationCreate.model_validate(message)
            with SessionLocal() as db:
                operation = append_operation(
                    db,
                    tenant_id=tenant_id,
                    room_id=room_id,
                    operation_id=operation_payload.operation_id,
                    actor_id=actor_id,
                    operation_type=operation_payload.operation_type,
                    payload=operation_payload.payload,
                )
            operation_message = {
                "type": "operation",
                "room_id": room_id,
                "operation_id": operation.operation_id,
                "actor_id": actor_id,
                "operation_type": operation.operation_type,
                "payload": json.loads(operation.payload),
                "created_at": operation.created_at.isoformat(),
            }
            await websocket.send_json(operation_message)
            await _whiteboard_hub.broadcast(room_key, operation_message, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        _whiteboard_hub.leave(room_key, websocket)


def _publish_transcript_event(event: dict) -> str:
    redis_url = get_settings().redis_url
    if not redis_url:
        raise HTTPException(status_code=503, detail="Agent event transport is not configured")
    try:
        import redis

        client = redis.Redis.from_url(redis_url, decode_responses=True)
        return str(client.xadd("class:transcript:chunks", {"data": json.dumps(event, ensure_ascii=False)}))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Agent event transport is unavailable") from exc


def _publish_audio_event(event: dict) -> str:
    redis_url = get_settings().redis_url
    if not redis_url:
        raise HTTPException(status_code=503, detail="Agent event transport is not configured")
    try:
        import redis

        client = redis.Redis.from_url(redis_url, decode_responses=True)
        return str(client.xadd("class:audio:chunks", {"data": json.dumps(event, ensure_ascii=False)}))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Agent event transport is unavailable") from exc


@router.post("/agent/events/audio", status_code=202)
async def publish_audio_chunk(
    audio: UploadFile = File(...),
    session_id: str = Form(..., min_length=1, max_length=160),
    dispatch_mode: str = Form(default="auto", pattern="^(auto|manual)$"),
    claims: dict = Depends(require_roles("admin", "teacher")),
):
    allowed_types = {"audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/webm", "audio/ogg"}
    if audio.content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Unsupported audio content type")
    raw_audio = await audio.read()
    if not raw_audio or len(raw_audio) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio must be between 1 byte and 10 MB")
    tenant_id = claims.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Invalid tenant context")
    stream_id = _publish_audio_event({
        "type": "audio_chunk",
        "session_id": session_id,
        "tenant_id": tenant_id,
        "actor_user_id": claims.get("sub"),
        "mime_type": audio.content_type,
        "audio_b64": b64encode(raw_audio).decode("ascii"),
        "dispatch_mode": dispatch_mode,
    })
    return {"accepted": True, "stream": "class:audio:chunks", "stream_id": stream_id}


@router.post("/agent/events/transcript", status_code=202)
def publish_transcript_chunk(
    payload: TranscriptChunkCreate,
    claims: dict = Depends(require_roles("admin", "teacher")),
):
    tenant_id = claims.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Invalid tenant context")
    stream_id = _publish_transcript_event({
        "type": "transcript_chunk",
        "session_id": payload.session_id,
        "raw_text": payload.raw_text,
        "priority": payload.priority,
        "tenant_id": tenant_id,
        "actor_user_id": claims.get("sub"),
    })
    return {"accepted": True, "stream": "class:transcript:chunks", "stream_id": stream_id}


@router.get("/agent/results")
def list_agent_results(
    session_id: str,
    claims: dict = Depends(current_claims),
):
    redis_url = get_settings().redis_url
    tenant_id = claims.get("tenant_id")
    if not redis_url or not tenant_id:
        raise HTTPException(status_code=503, detail="Agent result transport is not configured")
    try:
        import redis

        client = redis.Redis.from_url(redis_url, decode_responses=True)
        entries = client.xrevrange("class:agent:results", count=20)
        results = []
        for stream_id, fields in entries:
            raw_data = fields.get("data")
            if not raw_data:
                continue
            data = json.loads(raw_data)
            if data.get("tenant_id") == tenant_id and data.get("session_id") == session_id:
                data["stream_id"] = stream_id
                results.append(data)
        return results
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Agent result transport is unavailable") from exc

@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(
        select(User).where(
            User.tenant_id == payload.tenant_id,
            User.email == payload.email,
            User.active.is_(True),
        )
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return LoginResponse(
        access_token=create_access_token(user.id, user.tenant_id, user.role),
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
    )


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/dashboard/summary")
def dashboard_summary(
    tenant_id: UUID = Depends(tenant_context),
    db: Session = Depends(get_db),
) -> dict:
    students = db.scalar(
        select(func.count(Student.id)).where(
            Student.tenant_id == tenant_id,
            Student.active.is_(True),
        )
    )
    courses = db.scalar(
        select(func.count(Course.id)).where(
            Course.tenant_id == tenant_id,
            Course.active.is_(True),
        )
    )
    enrollments = db.scalar(
        select(func.count(Enrollment.id)).where(
            Enrollment.tenant_id == tenant_id,
            Enrollment.active.is_(True),
        )
    )
    average_grade = db.scalar(
        select(func.avg(Grade.score)).where(
            Grade.tenant_id == tenant_id,
        )
    )
    attendance_records = db.scalar(
        select(func.count(Attendance.id)).where(
            Attendance.tenant_id == tenant_id,
        )
    )
    present_records = db.scalar(
        select(func.count(Attendance.id)).where(
            Attendance.tenant_id == tenant_id,
            Attendance.present.is_(True),
        )
    )
    attendance_rate = 0.0
    if attendance_records:
        attendance_rate = float(present_records or 0) / float(attendance_records)
    return {
        "tenant_id": str(tenant_id),
        "students": int(students or 0),
        "courses": int(courses or 0),
        "enrollments": int(enrollments or 0),
        "average_grade": float(average_grade or 0),
        "attendance_rate": attendance_rate,
        "health": "ok",
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/reports/executive-summary")
def executive_summary(
    tenant_id: UUID = Depends(tenant_context),
    db: Session = Depends(get_db),
) -> dict:
    students = db.scalar(
        select(func.count(Student.id)).where(
            Student.tenant_id == tenant_id,
            Student.active.is_(True),
        )
    )
    courses = db.scalar(
        select(func.count(Course.id)).where(
            Course.tenant_id == tenant_id,
            Course.active.is_(True),
        )
    )
    enrollments = db.scalar(
        select(func.count(Enrollment.id)).where(
            Enrollment.tenant_id == tenant_id,
            Enrollment.active.is_(True),
        )
    )
    average_grade = db.scalar(
        select(func.avg(Grade.score)).where(
            Grade.tenant_id == tenant_id,
        )
    )
    attendance_records = db.scalar(
        select(func.count(Attendance.id)).where(
            Attendance.tenant_id == tenant_id,
        )
    )
    present_records = db.scalar(
        select(func.count(Attendance.id)).where(
            Attendance.tenant_id == tenant_id,
            Attendance.present.is_(True),
        )
    )
    attendance_rate = 0.0
    if attendance_records:
        attendance_rate = float(present_records or 0) / float(attendance_records)
    outstanding_invoices_cents = db.scalar(
        select(func.coalesce(func.sum(Invoice.amount_cents), 0)).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status == InvoiceStatus.pending.value,
        )
    )
    return {
        "tenant_id": str(tenant_id),
        "students": int(students or 0),
        "courses": int(courses or 0),
        "enrollments": int(enrollments or 0),
        "average_grade": float(average_grade or 0),
        "attendance_rate": attendance_rate,
        "outstanding_invoices_cents": int(outstanding_invoices_cents or 0),
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/staff/roster")
def list_staff_roster(
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    if claims.get("role") not in {"admin", "staff", "academic_coordinator"}:
        raise HTTPException(status_code=403, detail="Staff roster requires an administrative role")
    users = db.scalars(
        select(User)
        .where(User.tenant_id == tenant_id, User.active.is_(True))
        .order_by(User.role, User.email)
    ).all()
    return [
        {
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
            "active": user.active,
            "student_id": str(user.student_id) if user.student_id else None,
        }
        for user in users
    ]


@router.get("/staff/workload")
def list_staff_workload(
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    if claims.get("role") not in {"admin", "staff", "academic_coordinator"}:
        raise HTTPException(status_code=403, detail="Staff workload requires an administrative role")
    rows = db.execute(
        select(
            TeacherCourse.teacher_user_id,
            func.count(TeacherCourse.id).label("course_count"),
        )
        .where(
            TeacherCourse.tenant_id == tenant_id,
            TeacherCourse.active.is_(True),
        )
        .group_by(TeacherCourse.teacher_user_id)
        .order_by(func.count(TeacherCourse.id).desc(), TeacherCourse.teacher_user_id)
    ).all()
    return [
        {
            "teacher_user_id": str(row.teacher_user_id),
            "course_count": int(row.course_count),
            "role": "teacher",
        }
        for row in rows
    ]


@router.get("/students", response_model=list[StudentRead])
def list_students(
    tenant_id: UUID = Depends(tenant_context),
    db: Session = Depends(get_db),
):
    return list(
        db.scalars(
            select(Student)
            .where(Student.tenant_id == tenant_id, Student.active.is_(True))
            .order_by(Student.last_name, Student.first_name)
        )
    )


def _current_student(
    claims: dict, tenant_id: UUID, db: Session
) -> Student:
    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid user identity") from exc
    student = db.scalar(
        select(Student)
        .join(User, User.student_id == Student.id)
        .where(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.active.is_(True),
            Student.tenant_id == tenant_id,
            Student.active.is_(True),
        )
    )
    if student is None:
        raise HTTPException(status_code=404, detail="Authenticated user has no active student profile")
    return student


@router.get("/students/me/courses", response_model=list[CourseRead])
def list_my_courses(
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    student = _current_student(claims, tenant_id, db)
    return list(
        db.scalars(
            select(Course)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .where(
                Enrollment.student_id == student.id,
                Enrollment.tenant_id == tenant_id,
                Enrollment.active.is_(True),
                Course.tenant_id == tenant_id,
                Course.active.is_(True),
            )
            .order_by(Course.name)
        )
    )


@router.get("/students/me/grades", response_model=list[GradeRead])
def list_my_grades(
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    student = _current_student(claims, tenant_id, db)
    return list(
        db.scalars(
            select(Grade)
            .where(Grade.student_id == student.id, Grade.tenant_id == tenant_id)
            .order_by(Grade.created_at.desc())
        )
    )


@router.get("/students/me/attendance")
def list_my_attendance(
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    student = _current_student(claims, tenant_id, db)
    records = db.scalars(
        select(Attendance)
        .where(Attendance.student_id == student.id, Attendance.tenant_id == tenant_id)
        .order_by(Attendance.session_date.desc())
    ).all()
    return [
        {
            "id": record.id,
            "course_id": record.course_id,
            "session_date": record.session_date,
            "present": record.present,
        }
        for record in records
    ]


@router.get("/guardians/me/students")
def list_guardian_students(
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    guardian_id = UUID(str(claims["sub"]))
    links = db.scalars(
        select(GuardianStudent).where(
            GuardianStudent.tenant_id == tenant_id,
            GuardianStudent.guardian_user_id == guardian_id,
            GuardianStudent.active.is_(True),
        )
    ).all()
    student_ids = [link.student_id for link in links]
    if not student_ids:
        return []
    students = db.scalars(
        select(Student).where(Student.id.in_(student_ids), Student.tenant_id == tenant_id, Student.active.is_(True))
    ).all()
    return [{"id": student.id, "first_name": student.first_name, "last_name": student.last_name} for student in students]


@router.get("/guardians/me/students/{student_id}/grades", response_model=list[GradeRead])
def list_guardian_student_grades(
    student_id: UUID,
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    guardian_id = UUID(str(claims["sub"]))
    linked = db.scalar(
        select(GuardianStudent).where(
            GuardianStudent.tenant_id == tenant_id,
            GuardianStudent.guardian_user_id == guardian_id,
            GuardianStudent.student_id == student_id,
            GuardianStudent.active.is_(True),
        )
    )
    if linked is None:
        raise HTTPException(status_code=404, detail="Student is not linked to this guardian")
    return list(
        db.scalars(
            select(Grade).where(Grade.tenant_id == tenant_id, Grade.student_id == student_id).order_by(Grade.created_at.desc())
        )
    )


@router.get("/teachers/me/courses", response_model=list[CourseRead])
def list_teacher_courses(
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    teacher_id = UUID(str(claims["sub"]))
    return list(
        db.scalars(
            select(Course)
            .join(TeacherCourse, TeacherCourse.course_id == Course.id)
            .where(
                TeacherCourse.teacher_user_id == teacher_id,
                TeacherCourse.tenant_id == tenant_id,
                TeacherCourse.active.is_(True),
                Course.tenant_id == tenant_id,
                Course.active.is_(True),
            )
        )
    )


@router.get("/teachers/me/courses/{course_id}/grades", response_model=list[GradeRead])
def list_teacher_course_grades(
    course_id: UUID,
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    teacher_id = UUID(str(claims["sub"]))
    assigned = db.scalar(
        select(TeacherCourse).where(
            TeacherCourse.teacher_user_id == teacher_id,
            TeacherCourse.course_id == course_id,
            TeacherCourse.tenant_id == tenant_id,
            TeacherCourse.active.is_(True),
        )
    )
    if assigned is None:
        raise HTTPException(status_code=404, detail="Course is not assigned to this teacher")
    return list(db.scalars(select(Grade).where(Grade.course_id == course_id, Grade.tenant_id == tenant_id)))


@router.post("/students", response_model=StudentRead, status_code=201)
def create_student(
    payload: StudentCreate,
    tenant_id: UUID = Depends(tenant_context),
    db: Session = Depends(get_db),
):
    existing = db.scalar(
        select(Student).where(
            Student.tenant_id == tenant_id,
            Student.document_number == payload.document_number,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Student document already exists")
    student = Student(tenant_id=tenant_id, **payload.model_dump())
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@router.get("/courses", response_model=list[CourseRead])
def list_courses(
    tenant_id: UUID = Depends(tenant_context),
    db: Session = Depends(get_db),
):
    return list(
        db.scalars(
            select(Course)
            .where(Course.tenant_id == tenant_id, Course.active.is_(True))
            .order_by(Course.name)
        )
    )


@router.post("/courses", response_model=CourseRead, status_code=201)
def create_course(
    payload: CourseCreate,
    tenant_id: UUID = Depends(tenant_context),
    db: Session = Depends(get_db),
):
    if db.scalar(
        select(Course).where(
            Course.tenant_id == tenant_id,
            Course.code == payload.code,
        )
    ):
        raise HTTPException(status_code=409, detail="Course code already exists")
    course = Course(tenant_id=tenant_id, **payload.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.post("/curriculum/grade-levels", response_model=GradeLevelRead, status_code=201)
def create_grade_level(
    payload: GradeLevelCreate,
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    if db.scalar(select(GradeLevel).where(GradeLevel.tenant_id == tenant_id, GradeLevel.code == payload.code)):
        raise HTTPException(status_code=409, detail="Grade level code already exists")
    grade_level = GradeLevel(tenant_id=tenant_id, **payload.model_dump())
    db.add(grade_level)
    db.flush()
    record_audit_event(db, tenant_id=tenant_id, actor_user_id=UUID(claims["sub"]), entity_name="grade_levels", entity_id=str(grade_level.id), action="CREATE", details=payload.model_dump())
    db.commit()
    db.refresh(grade_level)
    return grade_level


@router.get("/curriculum/grade-levels", response_model=list[GradeLevelRead])
def list_grade_levels(tenant_id: UUID = Depends(tenant_context), db: Session = Depends(get_db)):
    return repository_list_grade_levels(db, tenant_id)


@router.post("/curriculum/subjects", response_model=SubjectRead, status_code=201)
def create_subject(
    payload: SubjectCreate,
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    if db.scalar(select(Subject).where(Subject.tenant_id == tenant_id, Subject.code == payload.code)):
        raise HTTPException(status_code=409, detail="Subject code already exists")
    subject = Subject(tenant_id=tenant_id, **payload.model_dump())
    db.add(subject)
    db.flush()
    record_audit_event(db, tenant_id=tenant_id, actor_user_id=UUID(claims["sub"]), entity_name="subjects", entity_id=str(subject.id), action="CREATE", details=payload.model_dump())
    db.commit()
    db.refresh(subject)
    return subject


@router.get("/curriculum/subjects", response_model=list[SubjectRead])
def list_subjects(tenant_id: UUID = Depends(tenant_context), db: Session = Depends(get_db)):
    return repository_list_subjects(db, tenant_id)


@router.post("/curriculum/standards", response_model=CurriculumStandardRead, status_code=201)
def create_curriculum_standard(
    payload: CurriculumStandardCreate,
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    if db.scalar(select(CurriculumStandard).where(CurriculumStandard.tenant_id == tenant_id, CurriculumStandard.code == payload.code)):
        raise HTTPException(status_code=409, detail="Curriculum standard code already exists")
    standard = CurriculumStandard(tenant_id=tenant_id, **payload.model_dump())
    db.add(standard)
    db.flush()
    record_audit_event(db, tenant_id=tenant_id, actor_user_id=UUID(claims["sub"]), entity_name="curriculum_standards", entity_id=str(standard.id), action="CREATE", details=payload.model_dump())
    db.commit()
    db.refresh(standard)
    return standard


@router.get("/curriculum/standards", response_model=list[CurriculumStandardRead])
def list_curriculum_standards(tenant_id: UUID = Depends(tenant_context), db: Session = Depends(get_db)):
    return repository_list_standards(db, tenant_id)


@router.post("/admissions/applications", response_model=AdmissionApplicationRead, status_code=201)
def decide_admission_application(
    payload: AdmissionApplicationCreate,
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    eligibility = check_age_eligibility(
        payload.birth_date,
        payload.grade_min_age_years,
        payload.cutoff_date,
        tolerance_days=payload.tolerance_days,
    )
    application = AdmissionApplication(
        tenant_id=tenant_id,
        applicant_name=payload.applicant_name.strip(),
        birth_date=payload.birth_date,
        grade_level_code=payload.grade_level_code.strip(),
    )
    db.add(application)
    db.flush()
    domain_application = DomainApplication(
        id=application.id,
        tenant_id=tenant_id,
        applicant_name=application.applicant_name,
        birth_date=application.birth_date,
        grade_level_code=application.grade_level_code,
    )
    decision = decide_enrollment(
        domain_application,
        eligibility,
        available_seats=payload.available_seats,
        waitlist=_admission_waitlists,
    )
    application.status = decision.status
    application.decision_reason = decision.reason
    application.requires_human_review = decision.requires_human_review
    application.waitlist_position = decision.waitlist_entry.position if decision.waitlist_entry else None
    if decision.waitlist_entry:
        application.waitlist_position = next_waitlist_position(db, tenant_id, application.grade_level_code)
        db.add(
            AdmissionWaitlistEntry(
                tenant_id=tenant_id,
                application_id=application.id,
                grade_level_code=application.grade_level_code,
                position=application.waitlist_position,
                reason=decision.reason,
            )
        )
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=UUID(claims["sub"]),
        entity_name="admission_applications",
        entity_id=str(application.id),
        action=decision.status.upper(),
        details={"reason": decision.reason, "requires_human_review": decision.requires_human_review},
    )
    db.commit()
    db.refresh(application)
    return application


@router.get("/admissions/applications", response_model=list[AdmissionApplicationRead])
def list_admission_applications(
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    if claims.get("role") not in {"admin", "staff", "academic_coordinator"}:
        raise HTTPException(status_code=403, detail="Admission applications require an administrative role")
    return repository_list_applications(db, tenant_id)


@router.post("/enrollments", response_model=EnrollmentRead, status_code=201)
def create_enrollment(
    payload: EnrollmentCreate,
    tenant_id: UUID = Depends(tenant_context),
    db: Session = Depends(get_db),
):
    student = db.scalar(
        select(Student).where(
            Student.id == payload.student_id,
            Student.tenant_id == tenant_id,
            Student.active.is_(True),
        )
    )
    course = db.scalar(
        select(Course).where(
            Course.id == payload.course_id,
            Course.tenant_id == tenant_id,
            Course.active.is_(True),
        )
    )
    if not student or not course:
        raise HTTPException(status_code=404, detail="Student or course not found in tenant")
    existing = db.scalar(
        select(Enrollment).where(
            Enrollment.tenant_id == tenant_id,
            Enrollment.student_id == payload.student_id,
            Enrollment.course_id == payload.course_id,
            Enrollment.active.is_(True),
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Student already enrolled in this course")

    enrollment = Enrollment(
        tenant_id=tenant_id,
        student_id=payload.student_id,
        course_id=payload.course_id,
        active=True,
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment


@router.post("/grades", response_model=GradeRead, status_code=201)
def create_grade(
    payload: GradeCreate,
    tenant_id: UUID = Depends(tenant_context),
    db: Session = Depends(get_db),
):
    student = db.scalar(
        select(Student).where(
            Student.id == payload.student_id,
            Student.tenant_id == tenant_id,
            Student.active.is_(True),
        )
    )
    course = db.scalar(
        select(Course).where(
            Course.id == payload.course_id,
            Course.tenant_id == tenant_id,
            Course.active.is_(True),
        )
    )
    if not student or not course:
        raise HTTPException(status_code=404, detail="Student or course not found in tenant")
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.tenant_id == tenant_id,
            Enrollment.student_id == payload.student_id,
            Enrollment.course_id == payload.course_id,
            Enrollment.active.is_(True),
        )
    )
    if not enrollment:
        raise HTTPException(status_code=400, detail="Student is not enrolled in this course")

    grade = Grade(
        tenant_id=tenant_id,
        student_id=payload.student_id,
        course_id=payload.course_id,
        score=payload.score,
        comment=payload.comment,
    )
    db.add(grade)
    db.commit()
    db.refresh(grade)
    return grade


@router.post("/attendances", response_model=AttendanceRead, status_code=201)
def create_attendance(
    payload: AttendanceCreate,
    tenant_id: UUID = Depends(tenant_context),
    db: Session = Depends(get_db),
):
    student = db.scalar(
        select(Student).where(
            Student.id == payload.student_id,
            Student.tenant_id == tenant_id,
            Student.active.is_(True),
        )
    )
    course = db.scalar(
        select(Course).where(
            Course.id == payload.course_id,
            Course.tenant_id == tenant_id,
            Course.active.is_(True),
        )
    )
    if not student or not course:
        raise HTTPException(status_code=404, detail="Student or course not found in tenant")
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.tenant_id == tenant_id,
            Enrollment.student_id == payload.student_id,
            Enrollment.course_id == payload.course_id,
            Enrollment.active.is_(True),
        )
    )
    if not enrollment:
        raise HTTPException(status_code=400, detail="Student is not enrolled in this course")

    existing = db.scalar(
        select(Attendance).where(
            Attendance.tenant_id == tenant_id,
            Attendance.student_id == payload.student_id,
            Attendance.course_id == payload.course_id,
            Attendance.session_date == payload.session_date,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Attendance already recorded for this student and date")

    attendance = Attendance(
        tenant_id=tenant_id,
        student_id=payload.student_id,
        course_id=payload.course_id,
        session_date=payload.session_date,
        present=payload.present,
    )
    db.add(attendance)
    db.commit()
    db.refresh(attendance)
    return attendance


@router.get("/billing/invoices", response_model=list[InvoiceRead])
def list_invoices(
    tenant_id: UUID = Depends(tenant_context),
    db: Session = Depends(get_db),
):
    return list(
        db.scalars(
            select(Invoice)
            .where(Invoice.tenant_id == tenant_id)
            .order_by(Invoice.created_at.desc())
        )
    )


@router.post("/billing/invoices", response_model=InvoiceRead, status_code=201)
def create_invoice(
    payload: InvoiceCreate,
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    student = db.scalar(
        select(Student).where(
            Student.id == payload.student_id,
            Student.tenant_id == tenant_id,
            Student.active.is_(True),
        )
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found in tenant")

    invoice = Invoice(
        tenant_id=tenant_id,
        student_id=payload.student_id,
        concept=payload.concept,
        amount_cents=payload.amount_cents,
        currency=payload.currency,
        due_date=payload.due_date,
        status=InvoiceStatus.pending.value,
    )
    db.add(invoice)
    db.flush()
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=UUID(claims["sub"]),
        entity_name="invoices",
        entity_id=str(invoice.id),
        action="CREATE",
        details={
            "student_id": str(invoice.student_id),
            "concept": invoice.concept,
            "amount_cents": invoice.amount_cents,
            "currency": invoice.currency,
            "status": invoice.status,
        },
    )
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post("/billing/invoices/{invoice_id}/pay", response_model=InvoiceRead)
def pay_invoice(
    invoice_id: UUID,
    payload: PayInvoiceRequest,
    tenant_id: UUID = Depends(tenant_context),
    claims: dict = Depends(current_claims),
    db: Session = Depends(get_db),
):
    invoice = db.scalar(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == tenant_id,
        )
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found in tenant")
    if invoice.status == InvoiceStatus.paid.value:
        raise HTTPException(status_code=400, detail="Invoice already paid")

    payment_reference = f"MOCK-{uuid4().hex[:12]}"
    invoice.status = InvoiceStatus.paid.value
    invoice.paid_at = datetime.now(UTC)
    invoice.payment_reference = payment_reference
    db.flush()
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=UUID(claims["sub"]),
        entity_name="invoices",
        entity_id=str(invoice.id),
        action="PAY",
        details={
            "status": invoice.status,
            "payment_reference": payment_reference,
            "amount_cents": invoice.amount_cents,
        },
    )
    db.commit()
    db.refresh(invoice)
    return invoice

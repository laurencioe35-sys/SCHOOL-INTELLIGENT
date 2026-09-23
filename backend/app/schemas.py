from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StudentCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    document_number: str = Field(min_length=3, max_length=80)

class LoginRequest(BaseModel):
    tenant_id: UUID
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    tenant_id: UUID
    role: str


class PlatformSubscriptionUpdate(BaseModel):
    plan: str | None = Field(default=None, max_length=50)
    status: str | None = Field(default=None, max_length=30)


class TranscriptChunkCreate(BaseModel):
    session_id: str = Field(min_length=1, max_length=160)
    raw_text: str = Field(min_length=1, max_length=12000)
    priority: str = Field(default="normal", pattern="^(urgent|high|normal|low)$")


class WhiteboardOperationCreate(BaseModel):
    operation_id: str = Field(min_length=1, max_length=120)
    operation_type: str = Field(min_length=1, max_length=40)
    payload: dict[str, object] = Field(default_factory=dict)


class StudentRead(StudentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    active: bool


class CourseCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=160)


class CourseRead(CourseCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    active: bool


class EnrollmentCreate(BaseModel):
    student_id: UUID
    course_id: UUID


class EnrollmentRead(EnrollmentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    active: bool


class GradeCreate(BaseModel):
    student_id: UUID
    course_id: UUID
    score: int = Field(ge=0, le=100)
    comment: str | None = None


class GradeRead(GradeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    created_at: datetime


class AttendanceCreate(BaseModel):
    student_id: UUID
    course_id: UUID
    session_date: date
    present: bool = True


class AttendanceRead(AttendanceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    created_at: datetime


class InvoiceCreate(BaseModel):
    student_id: UUID
    concept: str = Field(min_length=2, max_length=160)
    amount_cents: int = Field(gt=0)
    currency: str = "COP"
    due_date: datetime


class InvoiceRead(InvoiceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    status: str
    paid_at: datetime | None = None
    payment_reference: str | None = None
    created_at: datetime


class PayInvoiceRequest(BaseModel):
    payment_method_token: str = Field(min_length=3, max_length=200)


class GradeLevelCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = Field(ge=0)


class GradeLevelRead(GradeLevelCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    active: bool


class SubjectCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    area: str = Field(min_length=1, max_length=120)


class SubjectRead(SubjectCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    active: bool


class CurriculumStandardCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1)
    area: str = Field(min_length=1, max_length=120)
    grade_level_code: str = Field(min_length=1, max_length=40)
    is_placeholder: bool = False


class CurriculumStandardRead(CurriculumStandardCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    active: bool


class AdmissionApplicationCreate(BaseModel):
    applicant_name: str = Field(min_length=1, max_length=180)
    birth_date: date
    grade_level_code: str = Field(min_length=1, max_length=40)
    grade_min_age_years: int = Field(ge=0, le=30)
    cutoff_date: date
    available_seats: int = Field(ge=0)
    tolerance_days: int = Field(default=30, ge=0, le=365)


class AdmissionApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    applicant_name: str
    birth_date: date
    grade_level_code: str
    status: str
    decision_reason: str | None
    requires_human_review: bool
    waitlist_position: int | None
    created_at: datetime

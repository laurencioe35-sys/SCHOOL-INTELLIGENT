from uuid import uuid4

from app.db import SessionLocal, engine
from app.migrations import upgrade
from app.models import Course, Student, Tenant, User
from app.modules.colegio_virtual.virtual_classroom.repository import create_live_class, record_attendance


def test_live_class_and_attendance_are_durable_and_idempotent():
    upgrade(engine)
    tenant_id, course_id, teacher_id, student_id = uuid4(), uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        db.add_all([
            Tenant(id=tenant_id, name="Live school"),
            Course(id=course_id, tenant_id=tenant_id, code="LIVE", name="Live"),
            User(id=teacher_id, tenant_id=tenant_id, email="teacher-live@example.com", password_hash="hash", role="teacher"),
            Student(id=student_id, tenant_id=tenant_id, first_name="Sol", last_name="Luz", document_number="LIVE-1"),
        ])
        db.commit()
        live_class = create_live_class(db, tenant_id=tenant_id, course_id=course_id, teacher_user_id=teacher_id)
        first = record_attendance(db, tenant_id=tenant_id, live_class_id=live_class.id, student_id=student_id, status="PRESENT_PASSIVE", connected_minutes=85, interaction_events=0)
        second = record_attendance(db, tenant_id=tenant_id, live_class_id=live_class.id, student_id=student_id, status="PRESENT", connected_minutes=95, interaction_events=2)
        assert first.id == second.id
        assert second.attendance_status == "PRESENT"
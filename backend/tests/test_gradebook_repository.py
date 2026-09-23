from uuid import uuid4

from app.db import SessionLocal, engine
from app.migrations import upgrade
from app.models import Course, Enrollment, Student, Tenant
from app.modules.colegio_virtual.gradebook.repository import create_assignment, record_grade


def test_gradebook_assignment_and_grade_are_durable_and_tenant_scoped():
    upgrade(engine)
    tenant_id, student_id, course_id = uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        db.add_all([
            Tenant(id=tenant_id, name="Grade school"),
            Student(id=student_id, tenant_id=tenant_id, first_name="Leo", last_name="Sol", document_number="GB-1"),
            Course(id=course_id, tenant_id=tenant_id, code="BIO", name="Biologia"),
            Enrollment(tenant_id=tenant_id, student_id=student_id, course_id=course_id),
        ])
        db.commit()
        assignment = create_assignment(db, tenant_id=tenant_id, course_id=course_id, title="Quiz", category="tasks", max_score=100)
        first = record_grade(db, tenant_id=tenant_id, assignment_id=assignment.id, student_id=student_id, score=80)
        second = record_grade(db, tenant_id=tenant_id, assignment_id=assignment.id, student_id=student_id, score=90)
        assert first.id == second.id
        assert second.score == 90
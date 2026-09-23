from uuid import uuid4
from app.models import Student, Tenant, User

def test_student_requires_tenant():
    tenant = uuid4()
    student = Student(tenant_id=tenant, first_name="Ana", last_name="Lopez", document_number="100")
    assert student.tenant_id == tenant

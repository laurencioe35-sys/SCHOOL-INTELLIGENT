from datetime import date
from uuid import uuid4

from app.db import SessionLocal, engine
from app.migrations import upgrade
from app.models import AdmissionApplication, AdmissionWaitlistEntry, Tenant
from app.modules.colegio_virtual.admissions.repository import list_applications, list_waitlist, next_waitlist_position


def test_admissions_repository_is_tenant_scoped_and_positions_are_durable():
    upgrade(engine)
    tenant_a, tenant_b = uuid4(), uuid4()
    with SessionLocal() as db:
        db.add_all([Tenant(id=tenant_a, name="A"), Tenant(id=tenant_b, name="B")])
        db.flush()
        application = AdmissionApplication(tenant_id=tenant_a, applicant_name="Ana", birth_date=date(2017, 1, 1), grade_level_code="1")
        db.add(application)
        db.flush()
        db.add(AdmissionWaitlistEntry(tenant_id=tenant_a, application_id=application.id, grade_level_code="1", position=1, reason="No seats"))
        db.commit()
        assert next_waitlist_position(db, tenant_a, "1") == 2
        assert len(list_applications(db, tenant_a)) == 1
        assert len(list_waitlist(db, tenant_a, "1")) == 1
        assert list_applications(db, tenant_b) == []
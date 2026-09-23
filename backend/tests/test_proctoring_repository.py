from datetime import UTC, datetime
from uuid import uuid4

from app.db import SessionLocal, engine
from app.migrations import upgrade
from app.modules.colegio_virtual.proctoring.repository import list_flags, save_consent, save_integrity_flag


def test_proctoring_consent_and_flags_are_durable_without_sanctions():
    upgrade(engine)
    tenant_id, student_id, guardian_id = uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        consent = save_consent(db, tenant_id=tenant_id, student_id=student_id, guardian_user_id=guardian_id, scope=["tab_switch"], duration_minutes=60, viewer_role="academic_coordinator", verified_at=datetime.now(UTC))
        flag = save_integrity_flag(db, tenant_id=tenant_id, student_id=student_id, pattern="tab_switch", confidence=0.9, evidence={"count": 3})
        assert consent.student_id == student_id
        assert flag.sanction_applied is False
        assert len(list_flags(db, tenant_id=tenant_id, student_id=student_id)) == 1
from uuid import uuid4

import pytest

from app.db import SessionLocal, engine
from app.migrations import upgrade
from app.models import AcademicCertificateEvent, Student, Tenant
from app.modules.colegio_virtual.credentials.repository import issue_certificate, revoke_certificate, verify_certificate_publicly


def test_certificate_issue_verify_and_revoke_are_durable_and_append_only():
    upgrade(engine)
    tenant_id, student_id = uuid4(), uuid4()
    with SessionLocal() as db:
        db.add_all([
            Tenant(id=tenant_id, name="Certificate school"),
            Student(id=student_id, tenant_id=tenant_id, first_name="Eva", last_name="Sol", document_number="CERT-1"),
        ])
        db.commit()
        certificate = issue_certificate(
            db,
            tenant_id=tenant_id,
            student_id=student_id,
            signer_user_id="rector-1",
            signer_role="rector",
            document_hash="hash-1",
        )
        assert verify_certificate_publicly(db, certificate_id=certificate.id).document_hash == "hash-1"
        revoke_certificate(db, tenant_id=tenant_id, certificate_id=certificate.id, reason="Correction")
        events = db.query(AcademicCertificateEvent).filter(AcademicCertificateEvent.certificate_id == certificate.id).all()
        assert [event.action for event in events] == ["CREATE", "APPROVE", "UPDATE"]


def test_certificate_rejects_non_graduation_role():
    upgrade(engine)
    with SessionLocal() as db:
        with pytest.raises(PermissionError):
            issue_certificate(
                db,
                tenant_id=uuid4(),
                student_id=uuid4(),
                signer_user_id="teacher-1",
                signer_role="teacher",
                document_hash="hash-2",
            )
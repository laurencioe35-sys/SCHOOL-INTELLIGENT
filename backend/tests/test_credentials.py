import pytest

from app.modules.colegio_virtual.credentials.certificate_generator import evaluate_graduation
from app.modules.colegio_virtual.credentials.certificate_signature import (
    AUTHORIZED_GRADUATION_SIGNER_ROLES,
    CertificateStore,
)
from app.modules.colegio_virtual.credentials.transcript_service import build_transcript


def test_unsigned_report_card_is_omitted_from_transcript():
    transcript = build_transcript([
        {"course_id": "math", "final_grade": "90", "signed": True, "document_hash": "h1"},
        {"course_id": "science", "final_grade": "80", "signed": False, "document_hash": "h2"},
    ])
    assert [entry.course_id for entry in transcript] == ["math"]


def test_graduation_rejection_explains_missing_course():
    decision = evaluate_graduation({"math", "science"}, {"math"})
    assert decision.eligible is False
    assert decision.missing_courses == ("science",)
    assert "science" in decision.reason


def test_graduation_signer_roles_are_narrower_and_revoke_is_append_only():
    assert AUTHORIZED_GRADUATION_SIGNER_ROLES != {"academic_coordinator", "principal"}
    store = CertificateStore()
    certificate = store.issue("student-1", "rector", evaluate_graduation({"math"}, {"math"}))
    store.revoke(certificate.certificate_id, "Administrative correction")
    assert [event.action for event in store.events] == ["CREATE", "APPROVE", "UPDATE"]


def test_unauthorized_graduation_signer_is_rejected():
    with pytest.raises(PermissionError):
        CertificateStore().issue("student-1", "teacher", evaluate_graduation({"math"}, {"math"}))
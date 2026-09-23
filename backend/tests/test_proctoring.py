from datetime import UTC, datetime

import pytest

from app.modules.colegio_virtual.proctoring.exam_session_service import start_exam_session
from app.modules.colegio_virtual.proctoring.integrity_flagging import flag_interaction_pattern
from app.modules.colegio_virtual.proctoring.proctoring_disclosure import (
    ConsentRequiredError,
    ProctoringConsent,
)


def test_supervision_requires_verified_consent():
    with pytest.raises(ConsentRequiredError):
        start_exam_session("student-1", None)


def test_high_confidence_signal_notifies_without_sanction():
    flag = flag_interaction_pattern(
        student_id="student-1",
        pattern="long_paste",
        confidence=0.94,
        evidence={"characters": 1200, "timestamp": "2026-09-14T10:00:00Z"},
    )
    assert flag.notified_role == "academic_coordinator"
    assert flag.sanction_applied is False
    assert flag.evidence


def test_consented_session_uses_only_non_biometric_signals():
    consent = ProctoringConsent(
        "student-1",
        ("tab_switch", "response_timing", "long_paste"),
        60,
        "academic_coordinator",
        datetime.now(UTC),
    )
    session = start_exam_session("student-1", consent)
    assert "face_recognition" not in session.active_signals
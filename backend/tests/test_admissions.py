from datetime import date
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.audit import AuditLog
from app.db import SessionLocal
from app.main import app
from app.models import AdmissionWaitlistEntry
import pytest

from app.modules.colegio_virtual.admissions.application_intake import create_application
from app.modules.colegio_virtual.admissions.eligibility_check import check_age_eligibility
from app.modules.colegio_virtual.admissions.enrollment_service import decide_enrollment
from app.modules.colegio_virtual.admissions.waitlist_manager import WaitlistManager


def test_age_inside_tolerance_requires_human_review():
    result = check_age_eligibility(date(2020, 4, 15), 6, date(2026, 3, 31), tolerance_days=30)

    assert result.eligible is False
    assert result.requires_human_review is True
    assert "dentro del margen" in result.reason


def test_age_outside_tolerance_is_rejected_with_reason():
    result = check_age_eligibility(date(2020, 6, 1), 6, date(2026, 3, 31), tolerance_days=30)

    assert result.eligible is False
    assert result.requires_human_review is False
    assert "fuera del margen" in result.reason


def test_no_seat_moves_application_to_waitlist():
    application = create_application(
        tenant_id=uuid4(),
        applicant_name="Lucia Perez",
        birth_date=date(2018, 1, 1),
        grade_level_code="6",
    )
    waitlist = WaitlistManager()
    eligibility = check_age_eligibility(date(2018, 1, 1), 6, date(2026, 3, 31))

    decision = decide_enrollment(application, eligibility, available_seats=0, waitlist=waitlist)

    assert decision.status == "waitlisted"
    assert decision.reason
    assert decision.waitlist_entry is not None
    assert waitlist.entries_for("6")[0].application_id == application.id

def test_admission_api_persists_waitlist_decision_and_reason_in_audit():
    client = TestClient(app)
    tenant_id = uuid4()
    from app.security import create_access_token

    headers = {
        "Authorization": f"Bearer {create_access_token(user_id=uuid4(), tenant_id=tenant_id, role='admin')}"
    }
    response = client.post(
        "/api/v1/admissions/applications",
        headers=headers,
        json={
            "applicant_name": "Mateo Ruiz",
            "birth_date": "2017-01-01",
            "grade_level_code": "6",
            "grade_min_age_years": 6,
            "cutoff_date": "2026-03-31",
            "available_seats": 0,
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "waitlisted"
    assert response.json()["decision_reason"]
    assert response.json()["waitlist_position"] == 1
    with SessionLocal() as db:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.entity_id == response.json()["id"],
            )
        )
        assert audit is not None
        assert "reason" in audit.details
        waitlist_entry = db.scalar(
            select(AdmissionWaitlistEntry).where(
                AdmissionWaitlistEntry.application_id == UUID(response.json()["id"])
            )
        )
        assert waitlist_entry is not None
        assert waitlist_entry.position == 1
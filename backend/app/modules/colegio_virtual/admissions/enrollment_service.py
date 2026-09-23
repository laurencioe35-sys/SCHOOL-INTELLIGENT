from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from .application_intake import AdmissionApplication
from .eligibility_check import EligibilityResult
from .waitlist_manager import WaitlistEntry, WaitlistManager


@dataclass(frozen=True)
class EnrollmentDecision:
    status: str
    application_id: UUID
    enrollment_id: UUID | None
    reason: str
    requires_human_review: bool
    waitlist_entry: WaitlistEntry | None = None


def decide_enrollment(
    application: AdmissionApplication,
    eligibility: EligibilityResult,
    *,
    available_seats: int,
    waitlist: WaitlistManager,
) -> EnrollmentDecision:
    if not eligibility.eligible:
        return EnrollmentDecision(
            status="review" if eligibility.requires_human_review else "rejected",
            application_id=application.id,
            enrollment_id=None,
            reason=eligibility.reason,
            requires_human_review=eligibility.requires_human_review,
        )

    if available_seats <= 0:
        reason = "Sin cupos disponibles — solicitud enviada a lista de espera"
        entry = waitlist.enqueue(application.id, application.grade_level_code, reason)
        return EnrollmentDecision("waitlisted", application.id, None, reason, False, entry)

    return EnrollmentDecision(
        status="accepted",
        application_id=application.id,
        enrollment_id=uuid4(),
        reason="Cumple requisitos y existe cupo disponible",
        requires_human_review=False,
    )
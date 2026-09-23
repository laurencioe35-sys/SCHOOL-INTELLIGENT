from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class ProctoringConsent:
    student_id: str
    scope: tuple[str, ...]
    duration_minutes: int
    viewer_role: str
    verified_at: datetime


class ConsentRequiredError(PermissionError):
    pass


def verify_consent(consent: ProctoringConsent | None, requested_signal: str) -> None:
    if consent is None or requested_signal not in consent.scope:
        raise ConsentRequiredError("Verified consent is required before activating supervision")
    if consent.verified_at > datetime.now(UTC):
        raise ConsentRequiredError("Consent verification timestamp is invalid")
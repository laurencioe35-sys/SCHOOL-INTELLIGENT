from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


AUTHORIZED_GRADUATION_SIGNER_ROLES = {"principal", "rector"}


@dataclass(frozen=True)
class CertificateEvent:
    certificate_id: str
    action: str
    status: str
    reason: str


class CertificateStore:
    def __init__(self) -> None:
        self.events: list[CertificateEvent] = []

    def issue(self, student_id: str, signer_role: str, decision) -> CertificateEvent:
        if not decision.eligible:
            raise PermissionError(decision.reason)
        if signer_role not in AUTHORIZED_GRADUATION_SIGNER_ROLES:
            raise PermissionError("Signer is not authorized for graduation certificates")
        event = CertificateEvent(uuid4().hex, "CREATE", "approved", f"student={student_id}")
        self.events.append(event)
        self.events.append(CertificateEvent(event.certificate_id, "APPROVE", "approved", signer_role))
        return event

    def revoke(self, certificate_id: str, reason: str) -> CertificateEvent:
        event = CertificateEvent(certificate_id, "UPDATE", "revoked", reason)
        self.events.append(event)
        return event

    def verify_publicly(self, certificate_id: str) -> list[CertificateEvent]:
        return [event for event in self.events if event.certificate_id == certificate_id]
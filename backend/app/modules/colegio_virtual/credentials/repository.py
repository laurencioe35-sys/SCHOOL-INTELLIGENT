from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicCertificate, AcademicCertificateEvent

AUTHORIZED_GRADUATION_SIGNER_ROLES = {"principal", "rector"}


def issue_certificate(
    db: Session,
    *,
    tenant_id: UUID,
    student_id: UUID,
    signer_user_id: str,
    signer_role: str,
    document_hash: str,
) -> AcademicCertificate:
    if signer_role not in AUTHORIZED_GRADUATION_SIGNER_ROLES:
        raise PermissionError("Signer is not authorized for graduation certificates")
    certificate = AcademicCertificate(
        tenant_id=tenant_id,
        student_id=student_id,
        signed_by=signer_user_id,
        signed_role=signer_role,
        document_hash=document_hash,
        status="approved",
    )
    db.add(certificate)
    db.flush()
    db.add_all([
        AcademicCertificateEvent(
            tenant_id=tenant_id,
            certificate_id=certificate.id,
            action="CREATE",
            status="approved",
            reason=f"student={student_id}",
        ),
        AcademicCertificateEvent(
            tenant_id=tenant_id,
            certificate_id=certificate.id,
            action="APPROVE",
            status="approved",
            reason=f"signed_by={signer_user_id};role={signer_role}",
        ),
    ])
    db.commit()
    db.refresh(certificate)
    return certificate


def revoke_certificate(db: Session, *, tenant_id: UUID, certificate_id: UUID, reason: str) -> AcademicCertificateEvent:
    certificate = db.scalar(
        select(AcademicCertificate).where(
            AcademicCertificate.id == certificate_id,
            AcademicCertificate.tenant_id == tenant_id,
        )
    )
    if certificate is None:
        raise KeyError("Certificate not found in tenant")
    certificate.status = "revoked"
    event = AcademicCertificateEvent(
        tenant_id=tenant_id,
        certificate_id=certificate_id,
        action="UPDATE",
        status="revoked",
        reason=reason,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def verify_certificate_publicly(db: Session, *, certificate_id: UUID) -> AcademicCertificate | None:
    return db.scalar(select(AcademicCertificate).where(AcademicCertificate.id == certificate_id))
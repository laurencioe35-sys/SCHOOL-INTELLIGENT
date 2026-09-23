from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


AUTHORIZED_SIGNER_ROLES = {"academic_coordinator", "principal"}


@dataclass(frozen=True)
class SignedReportCard:
    pdf_path: str
    document_hash: str
    signed_by: str
    signed_at: datetime


class UnauthorizedSignerError(Exception):
    pass


async def sign_report_card(
    session,
    *,
    tenant_id: str,
    pdf_path: str,
    signer_user_id: str,
    signer_role: str,
    webauthn_assertion: dict,
) -> SignedReportCard:
    if signer_role not in AUTHORIZED_SIGNER_ROLES:
        raise UnauthorizedSignerError(f"Rol '{signer_role}' no está autorizado para firmar boletines")
    if not webauthn_assertion.get("verified", False):
        raise UnauthorizedSignerError("Verificación WebAuthn fallida — firma rechazada")
    if not Path(pdf_path).is_file():
        raise FileNotFoundError(pdf_path)
    document_hash = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
    return SignedReportCard(pdf_path, document_hash, signer_user_id, datetime.now(UTC))
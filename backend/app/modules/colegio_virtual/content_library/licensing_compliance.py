from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LicenseType(str, Enum):
    CREATIVE_COMMONS = "creative_commons"
    PUBLISHER_LICENSED = "publisher_licensed"
    PUBLIC_DOMAIN = "public_domain"
    INSTITUTION_OWNED = "institution_owned"
    UNKNOWN = "unknown"


ACCEPTED_LICENSE_TYPES = {
    LicenseType.CREATIVE_COMMONS,
    LicenseType.PUBLISHER_LICENSED,
    LicenseType.PUBLIC_DOMAIN,
    LicenseType.INSTITUTION_OWNED,
}


@dataclass(frozen=True)
class LicensingDecision:
    status: str
    reason: str


def evaluate_licensing(license_type: LicenseType, uploaded_by_role: str) -> LicensingDecision:
    if uploaded_by_role not in {"content_licensing_agent", "system_review"}:
        return LicensingDecision("pending_review", "Requiere verificación del Content-Licensing Agent")
    if license_type == LicenseType.UNKNOWN:
        return LicensingDecision("pending_review", "Tipo de licencia no declarado o no verificable")
    if license_type in ACCEPTED_LICENSE_TYPES:
        return LicensingDecision("approved", f"Licencia '{license_type.value}' verificada y aceptada")
    return LicensingDecision("rejected", f"Licencia '{license_type.value}' no está en la lista de tipos aceptados")
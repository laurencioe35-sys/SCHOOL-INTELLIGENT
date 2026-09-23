from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: str
    tenant_id: str
    certificate_fingerprint: str


def validate_device_identity(identity: DeviceIdentity) -> None:
    if not identity.device_id or not identity.tenant_id or not identity.certificate_fingerprint:
        raise ValueError("Device identity requires device, tenant, and certificate fingerprint")
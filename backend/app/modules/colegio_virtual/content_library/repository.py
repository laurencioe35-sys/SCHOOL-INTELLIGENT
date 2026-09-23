from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EducationalMaterial, EducationalMaterialVersion


def create_material(db: Session, *, tenant_id: UUID, title: str, content_ref: str, uploaded_by_role: str) -> EducationalMaterial:
    material = EducationalMaterial(
        tenant_id=tenant_id,
        title=title.strip(),
        content_ref=content_ref.strip(),
        uploaded_by_role=uploaded_by_role,
        licensing_status="pending_review",
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return material


def publish_version(
    db: Session,
    *,
    tenant_id: UUID,
    material_id: UUID,
    content_ref: str,
    published_by: str,
) -> EducationalMaterialVersion:
    material = db.scalar(
        select(EducationalMaterial).where(
            EducationalMaterial.id == material_id,
            EducationalMaterial.tenant_id == tenant_id,
            EducationalMaterial.active.is_(True),
        )
    )
    if material is None or material.licensing_status != "approved":
        raise PermissionError("Material must have approved licensing before publishing")
    version_number = int(
        db.scalar(
            select(func.max(EducationalMaterialVersion.version)).where(
                EducationalMaterialVersion.tenant_id == tenant_id,
                EducationalMaterialVersion.material_id == material_id,
            )
        )
        or 0
    ) + 1
    version = EducationalMaterialVersion(
        tenant_id=tenant_id,
        material_id=material_id,
        version=version_number,
        content_ref=content_ref,
        published_by=published_by,
        licensing_status=material.licensing_status,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version
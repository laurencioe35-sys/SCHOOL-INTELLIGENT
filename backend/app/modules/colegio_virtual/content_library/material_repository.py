from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True)
class Material:
    id: UUID
    tenant_id: UUID
    title: str
    content_ref: str
    uploaded_by_role: str
    licensing_status: str = "pending_review"


class MaterialRepository:
    def __init__(self) -> None:
        self._materials: dict[UUID, Material] = {}

    def create(self, *, tenant_id: UUID, title: str, content_ref: str, uploaded_by_role: str) -> Material:
        if not title.strip() or not content_ref.strip():
            raise ValueError("Material title and content reference are required")
        material = Material(uuid4(), tenant_id, title.strip(), content_ref.strip(), uploaded_by_role)
        self._materials[material.id] = material
        return material

    def get_for_tenant(self, material_id: UUID, tenant_id: UUID) -> Material:
        material = self._materials.get(material_id)
        if material is None or material.tenant_id != tenant_id:
            raise KeyError("Material not found in tenant")
        return material
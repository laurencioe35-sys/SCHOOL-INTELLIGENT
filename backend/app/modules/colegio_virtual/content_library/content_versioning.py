from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class MaterialVersion:
    material_id: str
    version: int
    content_ref: str
    published_at: datetime
    published_by: str
    licensing_status: str


class InMemoryMaterialVersionStore:
    def __init__(self) -> None:
        self._versions: dict[str, list[MaterialVersion]] = {}

    async def next_version(self, material_id: str) -> int:
        return len(self._versions.get(material_id, [])) + 1

    async def persist(self, version: MaterialVersion) -> MaterialVersion:
        self._versions.setdefault(version.material_id, []).append(version)
        return version

    def versions(self, material_id: str) -> list[MaterialVersion]:
        return list(self._versions.get(material_id, []))


async def publish_new_version(
    session: InMemoryMaterialVersionStore,
    *,
    material_id: str,
    content_ref: str,
    published_by: str,
    licensing_status: str,
) -> MaterialVersion:
    if licensing_status != "approved":
        raise PermissionError(f"No se puede publicar material con licensing_status='{licensing_status}'")
    version = MaterialVersion(
        material_id=material_id,
        version=await session.next_version(material_id),
        content_ref=content_ref,
        published_at=datetime.now(UTC),
        published_by=published_by,
        licensing_status=licensing_status,
    )
    return await session.persist(version)
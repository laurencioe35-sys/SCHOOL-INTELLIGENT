import pytest

from app.modules.colegio_virtual.content_library.content_versioning import (
    InMemoryMaterialVersionStore,
    publish_new_version,
)
from app.modules.colegio_virtual.content_library.licensing_compliance import (
    LicenseType,
    evaluate_licensing,
)
from app.modules.colegio_virtual.content_library.material_repository import MaterialRepository


def test_teacher_cannot_self_approve_own_material():
    decision = evaluate_licensing(LicenseType.PUBLIC_DOMAIN, uploaded_by_role="teacher")
    assert decision.status == "pending_review"


def test_unknown_license_never_auto_approved():
    decision = evaluate_licensing(LicenseType.UNKNOWN, uploaded_by_role="content_licensing_agent")
    assert decision.status == "pending_review"


@pytest.mark.asyncio
async def test_versions_are_immutable_and_unapproved_content_cannot_publish():
    store = InMemoryMaterialVersionStore()
    with pytest.raises(PermissionError):
        await publish_new_version(store, material_id="m1", content_ref="v1", published_by="teacher", licensing_status="pending_review")
    first = await publish_new_version(store, material_id="m1", content_ref="v1", published_by="agent", licensing_status="approved")
    second = await publish_new_version(store, material_id="m1", content_ref="v2", published_by="agent", licensing_status="approved")
    assert (first.version, second.version) == (1, 2)
    assert [version.content_ref for version in store.versions("m1")] == ["v1", "v2"]


def test_materials_start_pending_and_are_tenant_scoped():
    repository = MaterialRepository()
    tenant_a = __import__("uuid").uuid4()
    tenant_b = __import__("uuid").uuid4()
    material = repository.create(tenant_id=tenant_a, title="Guide", content_ref="s3://guide", uploaded_by_role="teacher")
    assert material.licensing_status == "pending_review"
    with pytest.raises(KeyError):
        repository.get_for_tenant(material.id, tenant_b)
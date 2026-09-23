from uuid import uuid4

import pytest

from app.db import SessionLocal, engine
from app.migrations import upgrade
from app.modules.colegio_virtual.content_library.repository import create_material, publish_version


def test_materials_start_pending_and_cannot_publish_until_approved():
    upgrade(engine)
    tenant_id = uuid4()
    with SessionLocal() as db:
        material = create_material(db, tenant_id=tenant_id, title="Guide", content_ref="ref-v1", uploaded_by_role="teacher")
        with pytest.raises(PermissionError):
            publish_version(db, tenant_id=tenant_id, material_id=material.id, content_ref="ref-v1", published_by="teacher")
        material.licensing_status = "approved"
        db.commit()
        first = publish_version(db, tenant_id=tenant_id, material_id=material.id, content_ref="ref-v1", published_by="licensing-agent")
        second = publish_version(db, tenant_id=tenant_id, material_id=material.id, content_ref="ref-v2", published_by="licensing-agent")
        assert (first.version, second.version) == (1, 2)
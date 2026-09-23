from uuid import uuid4

from app.db import SessionLocal
from app.models import CurriculumStandard, GradeLevel, Subject, Tenant
from app.modules.colegio_virtual.curriculum.repository import list_grade_levels, list_standards, list_subjects


def test_curriculum_catalog_repository_is_tenant_scoped():
    tenant_a, tenant_b = uuid4(), uuid4()
    with SessionLocal() as db:
        db.add_all([
            Tenant(id=tenant_a, name="A"),
            Tenant(id=tenant_b, name="B"),
            GradeLevel(tenant_id=tenant_a, code="1", name="Primero", sort_order=1),
            Subject(tenant_id=tenant_a, code="MAT", name="Matematicas", area="STEM"),
            CurriculumStandard(tenant_id=tenant_a, code="STD-1", description="Placeholder", area="STEM", grade_level_code="1", is_placeholder=True),
        ])
        db.commit()
        assert len(list_grade_levels(db, tenant_a)) == 1
        assert len(list_subjects(db, tenant_a)) == 1
        assert len(list_standards(db, tenant_a)) == 1
        assert list_grade_levels(db, tenant_b) == []
        assert list_subjects(db, tenant_b) == []
        assert list_standards(db, tenant_b) == []
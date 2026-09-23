import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

from app.main import app
from app.modules.colegio_virtual.curriculum.curriculum_standards import CurriculumStandard
from app.modules.colegio_virtual.curriculum.syllabus_builder import (
    InMemorySyllabusStore,
    PlaceholderStandardError,
    SyllabusTopic,
    TopicOrderingViolationError,
    publish_syllabus_version,
    validate_publishable_standard_references,
    validate_topic_ordering,
)


def test_curriculum_catalog_is_tenant_scoped():
    client = TestClient(app)
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())

    from app.security import create_access_token

    headers_a = {"Authorization": f"Bearer {create_access_token(user_id=uuid4(), tenant_id=tenant_a, role='admin')}"}
    headers_b = {"Authorization": f"Bearer {create_access_token(user_id=uuid4(), tenant_id=tenant_b, role='admin')}"}
    created = client.post(
        "/api/v1/curriculum/grade-levels",
        json={"code": "9", "name": "Noveno", "sort_order": 9},
        headers=headers_a,
    )

    assert created.status_code == 201, created.text
    assert client.get("/api/v1/curriculum/grade-levels", headers=headers_b).json() == []
    assert len(client.get("/api/v1/curriculum/grade-levels", headers=headers_a).json()) == 1


def test_rejects_prerequisite_scheduled_after_dependent_topic():
    topics = [
        SyllabusTopic("t1", "Ecuaciones cuadraticas", "MEN.MAT.9.1", ["t2"], 2),
        SyllabusTopic("t2", "Factorizacion", "MEN.MAT.9.2", [], 5),
    ]
    with pytest.raises(TopicOrderingViolationError):
        validate_topic_ordering(topics)


def test_rejects_placeholder_standard_in_production():
    topics = [SyllabusTopic("t1", "Tema de desarrollo", "MEN.PLACEHOLDER.1", [], 1)]
    standards = {
        "MEN.PLACEHOLDER.1": CurriculumStandard(
            "MEN.PLACEHOLDER.1", "Placeholder", "Matematicas", "9", is_placeholder=True
        )
    }
    with pytest.raises(PlaceholderStandardError):
        validate_publishable_standard_references(topics, standards, production=True)


@pytest.mark.asyncio
async def test_publishing_creates_new_syllabus_version():
    store = InMemorySyllabusStore()
    topics = [SyllabusTopic("t1", "Tema", "STD.1", [], 1)]

    first = await publish_syllabus_version(
        store, course_id="course-1", topics=topics, published_by="teacher-1", valid_standards={"STD.1"}
    )
    second = await publish_syllabus_version(
        store, course_id="course-1", topics=topics, published_by="teacher-1", valid_standards={"STD.1"}
    )

    assert (first.version, second.version) == (1, 2)
    assert len(store.versions("course-1")) == 2

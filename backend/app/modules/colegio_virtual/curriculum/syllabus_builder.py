"""Build and version syllabi with traceable curriculum standards."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from .curriculum_standards import CurriculumStandard


@dataclass(frozen=True)
class SyllabusTopic:
    id: str
    title: str
    standard_ref: str
    depends_on_topic_ids: list[str] = field(default_factory=list)
    week_number: int = 0


@dataclass(frozen=True)
class Syllabus:
    course_id: str
    version: int
    topics: list[SyllabusTopic]
    published_at: datetime
    published_by: str


class MissingStandardReferenceError(Exception):
    pass


class PlaceholderStandardError(Exception):
    pass


class TopicOrderingViolationError(Exception):
    pass


def validate_standard_references(topics: list[SyllabusTopic], valid_standards: set[str]) -> None:
    for topic in topics:
        if topic.standard_ref not in valid_standards:
            raise MissingStandardReferenceError(
                f"El tema '{topic.title}' referencia '{topic.standard_ref}', que no existe en los estándares vigentes"
            )


def validate_publishable_standard_references(
    topics: list[SyllabusTopic], standards: dict[str, CurriculumStandard], *, production: bool
) -> None:
    validate_standard_references(topics, set(standards))
    if production:
        for topic in topics:
            standard = standards[topic.standard_ref]
            if standard.is_placeholder:
                raise PlaceholderStandardError(
                    f"El tema '{topic.title}' referencia el placeholder '{standard.code}' y no puede publicarse en producción"
                )


def validate_topic_ordering(topics: list[SyllabusTopic]) -> None:
    week_by_id = {topic.id: topic.week_number for topic in topics}
    for topic in topics:
        for dependency_id in topic.depends_on_topic_ids:
            if dependency_id not in week_by_id:
                raise TopicOrderingViolationError(
                    f"'{topic.title}' depende de un tema inexistente: {dependency_id}"
                )
            if week_by_id[dependency_id] >= topic.week_number:
                raise TopicOrderingViolationError(
                    f"'{topic.title}' (semana {topic.week_number}) depende de un tema programado "
                    f"en la semana {week_by_id[dependency_id]} o después — el prerrequisito debe ir antes"
                )


class InMemorySyllabusStore:
    def __init__(self) -> None:
        self._versions: dict[str, list[Syllabus]] = {}

    async def next_version(self, course_id: str) -> int:
        return len(self._versions.get(course_id, [])) + 1

    async def persist(self, syllabus: Syllabus) -> Syllabus:
        self._versions.setdefault(syllabus.course_id, []).append(syllabus)
        return syllabus

    def versions(self, course_id: str) -> list[Syllabus]:
        return list(self._versions.get(course_id, []))


async def publish_syllabus_version(
    session: InMemorySyllabusStore,
    *,
    course_id: str,
    topics: list[SyllabusTopic],
    published_by: str,
    valid_standards: set[str],
) -> Syllabus:
    validate_standard_references(topics, valid_standards)
    validate_topic_ordering(topics)
    syllabus = Syllabus(
        course_id=course_id,
        version=await session.next_version(course_id),
        topics=list(topics),
        published_at=datetime.now(UTC),
        published_by=published_by,
    )
    return await session.persist(syllabus)

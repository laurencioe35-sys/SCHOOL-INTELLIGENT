from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogCourse:
    code: str
    name: str
    period_code: str
    grade_level_code: str
    subject_code: str
    active: bool = True


class CourseCatalog:
    def __init__(self, courses: list[CatalogCourse] | None = None) -> None:
        self._courses: dict[tuple[str, str], CatalogCourse] = {}
        for course in courses or []:
            self.add(course)

    def add(self, course: CatalogCourse) -> None:
        key = (course.period_code, course.code)
        if key in self._courses:
            raise ValueError(f"Course already exists in period: {course.code}")
        self._courses[key] = course

    def get(self, period_code: str, code: str) -> CatalogCourse:
        try:
            return self._courses[(period_code, code)]
        except KeyError as exc:
            raise KeyError(f"Unknown course in period: {code}") from exc

    def active_for_period(self, period_code: str) -> list[CatalogCourse]:
        return [
            course
            for (course_period, _), course in self._courses.items()
            if course_period == period_code and course.active
        ]

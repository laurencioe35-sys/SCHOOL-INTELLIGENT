from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from .grade_calculation_engine import GradeEntry


@dataclass(frozen=True)
class Assignment:
    id: UUID
    course_id: UUID
    title: str
    category: str
    max_score: Decimal


class AssignmentService:
    def __init__(self) -> None:
        self._assignments: dict[UUID, Assignment] = {}
        self._grades: dict[UUID, GradeEntry] = {}

    def create_assignment(
        self, *, course_id: UUID, title: str, category: str, max_score: Decimal
    ) -> Assignment:
        if not title.strip() or not category.strip():
            raise ValueError("Assignment title and category are required")
        if max_score <= 0:
            raise ValueError("max_score must be positive")
        assignment = Assignment(uuid4(), course_id, title.strip(), category.strip(), max_score)
        self._assignments[assignment.id] = assignment
        return assignment

    def grade_assignment(self, assignment_id: UUID, score: Decimal | None) -> GradeEntry:
        assignment = self._assignments.get(assignment_id)
        if assignment is None:
            raise KeyError("Assignment not found")
        if score is not None and (score < 0 or score > assignment.max_score):
            raise ValueError("Score must be within assignment range")
        entry = GradeEntry(assignment.category, score, assignment.max_score)
        self._grades[assignment_id] = entry
        return entry

    def grade_entries(self) -> list[GradeEntry]:
        return list(self._grades.values())
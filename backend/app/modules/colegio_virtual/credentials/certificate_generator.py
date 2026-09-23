from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraduationDecision:
    eligible: bool
    reason: str
    missing_courses: tuple[str, ...] = ()


def evaluate_graduation(required_courses: set[str], passed_courses: set[str]) -> GraduationDecision:
    missing = tuple(sorted(required_courses - passed_courses))
    if missing:
        return GraduationDecision(False, f"Faltan cursos requeridos: {', '.join(missing)}", missing)
    return GraduationDecision(True, "Cumple todos los cursos requeridos")
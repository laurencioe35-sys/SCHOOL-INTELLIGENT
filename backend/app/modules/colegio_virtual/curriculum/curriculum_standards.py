from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CurriculumStandard:
    code: str
    description: str
    area: str
    grade_level_code: str
    is_placeholder: bool = False
    active: bool = True


class CurriculumStandardCatalog:
    def __init__(self, standards: list[CurriculumStandard] | None = None) -> None:
        self._standards: dict[str, CurriculumStandard] = {}
        for standard in standards or []:
            self.add(standard)

    def add(self, standard: CurriculumStandard) -> None:
        if standard.code in self._standards:
            raise ValueError(f"Curriculum standard already exists: {standard.code}")
        self._standards[standard.code] = standard

    def get(self, code: str) -> CurriculumStandard:
        try:
            return self._standards[code]
        except KeyError as exc:
            raise KeyError(f"Unknown curriculum standard: {code}") from exc

    def active_codes(self) -> set[str]:
        return {standard.code for standard in self._standards.values() if standard.active}

    def production_codes(self) -> set[str]:
        return {
            standard.code
            for standard in self._standards.values()
            if standard.active and not standard.is_placeholder
        }

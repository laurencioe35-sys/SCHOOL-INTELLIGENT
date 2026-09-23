from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GradeLevel:
    code: str
    name: str
    sort_order: int
    active: bool = True


class GradeLevelCatalog:
    def __init__(self, levels: list[GradeLevel] | None = None) -> None:
        self._levels: dict[str, GradeLevel] = {}
        for level in levels or []:
            self.add(level)

    def add(self, level: GradeLevel) -> None:
        if level.code in self._levels:
            raise ValueError(f"Grade level already exists: {level.code}")
        self._levels[level.code] = level

    def get(self, code: str) -> GradeLevel:
        try:
            return self._levels[code]
        except KeyError as exc:
            raise KeyError(f"Unknown grade level: {code}") from exc

    def active(self) -> list[GradeLevel]:
        return sorted(
            (level for level in self._levels.values() if level.active),
            key=lambda level: level.sort_order,
        )

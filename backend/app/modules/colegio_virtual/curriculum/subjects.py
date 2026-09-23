from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Subject:
    code: str
    name: str
    area: str
    active: bool = True


class SubjectCatalog:
    def __init__(self, subjects: list[Subject] | None = None) -> None:
        self._subjects: dict[str, Subject] = {}
        for subject in subjects or []:
            self.add(subject)

    def add(self, subject: Subject) -> None:
        if subject.code in self._subjects:
            raise ValueError(f"Subject already exists: {subject.code}")
        self._subjects[subject.code] = subject

    def get(self, code: str) -> Subject:
        try:
            return self._subjects[code]
        except KeyError as exc:
            raise KeyError(f"Unknown subject: {code}") from exc

    def active(self) -> list[Subject]:
        return [subject for subject in self._subjects.values() if subject.active]

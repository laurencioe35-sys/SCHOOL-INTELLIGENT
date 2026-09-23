from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class WaitlistEntry:
    application_id: UUID
    grade_level_code: str
    position: int
    reason: str


class WaitlistManager:
    def __init__(self) -> None:
        self._entries: dict[str, list[WaitlistEntry]] = {}

    def enqueue(self, application_id: UUID, grade_level_code: str, reason: str) -> WaitlistEntry:
        entries = self._entries.setdefault(grade_level_code, [])
        entry = WaitlistEntry(application_id, grade_level_code, len(entries) + 1, reason)
        entries.append(entry)
        return entry

    def entries_for(self, grade_level_code: str) -> list[WaitlistEntry]:
        return list(self._entries.get(grade_level_code, []))
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LiveClassSession:
    id: str
    teacher_id: str
    recording_url: str | None = None
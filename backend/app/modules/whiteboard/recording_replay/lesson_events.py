from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class LessonEvent:
    event_id: str
    tenant_id: str
    lesson_id: str
    event_type: str
    t_offset_ms: int
    payload: dict[str, object]


class LessonEventLog:
    def __init__(self) -> None:
        self._events: list[LessonEvent] = []

    def append(self, *, tenant_id: str, lesson_id: str, event_type: str, t_offset_ms: int, payload: dict[str, object]) -> LessonEvent:
        if t_offset_ms < 0:
            raise ValueError("Event offset cannot be negative")
        event = LessonEvent(uuid4().hex, tenant_id, lesson_id, event_type, t_offset_ms, dict(payload))
        self._events.append(event)
        return event

    def timeline(self, tenant_id: str, lesson_id: str) -> tuple[LessonEvent, ...]:
        return tuple(
            sorted(
                (event for event in self._events if event.tenant_id == tenant_id and event.lesson_id == lesson_id),
                key=lambda event: (event.t_offset_ms, event.event_id),
            )
        )

    def update(self, *args, **kwargs) -> None:
        raise PermissionError("lesson_events is append-only")

    def delete(self, *args, **kwargs) -> None:
        raise PermissionError("lesson_events is append-only")
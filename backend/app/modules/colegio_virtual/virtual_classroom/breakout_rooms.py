from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BreakoutRoom:
    room_id: str
    participant_ids: tuple[str, ...]


class BreakoutRoomManager:
    def create(self, room_id: str, participant_ids: list[str]) -> BreakoutRoom:
        if not participant_ids:
            raise ValueError("A breakout room needs participants")
        return BreakoutRoom(room_id, tuple(participant_ids))
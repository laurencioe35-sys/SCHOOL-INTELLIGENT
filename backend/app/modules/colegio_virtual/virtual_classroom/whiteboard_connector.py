from __future__ import annotations

from .models import LiveClassSession


_rooms: set[str] = set()


async def attach_whiteboard_to_class_session(session: LiveClassSession) -> str:
    room_id = f"class.{session.id}"
    _rooms.add(room_id)
    return room_id


async def detach_whiteboard_from_class_session(session: LiveClassSession) -> None:
    _rooms.discard(f"class.{session.id}")
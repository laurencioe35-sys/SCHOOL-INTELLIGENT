from __future__ import annotations

import time


class MetaIdempotencyStore:
    def __init__(self, ttl_seconds: int = 7 * 24 * 60 * 60, clock=time.time) -> None:
        self.ttl_seconds, self.clock = ttl_seconds, clock
        self._events: dict[str, float] = {}

    def claim(self, event_id: str) -> bool:
        expires = self._events.get(event_id)
        if expires and expires > self.clock():
            return False
        self._events[event_id] = self.clock() + self.ttl_seconds
        return True
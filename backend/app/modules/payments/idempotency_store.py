from __future__ import annotations

import time


class IdempotencyStore:
    def __init__(self, ttl_seconds: int = 3600, clock=time.time) -> None:
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._values: dict[str, tuple[float, object]] = {}

    def get(self, key: str) -> object | None:
        record = self._values.get(key)
        if record is None:
            return None
        expires_at, value = record
        if expires_at <= self.clock():
            self._values.pop(key, None)
            return None
        return value

    def put(self, key: str, value: object) -> None:
        self._values[key] = (self.clock() + self.ttl_seconds, value)
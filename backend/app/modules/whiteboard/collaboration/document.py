from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter


@dataclass(frozen=True)
class StrokeOperation:
    tenant_id: str
    room_id: str
    actor_id: str
    operation_id: str
    points: tuple[tuple[float, float], ...]


class CollaborativeCanvas:
    def __init__(self, tenant_id: str, room_id: str) -> None:
        self.tenant_id = tenant_id
        self.room_id = room_id
        self._operations: dict[str, StrokeOperation] = {}

    def append(self, operation: StrokeOperation) -> None:
        if operation.tenant_id != self.tenant_id or operation.room_id != self.room_id:
            raise PermissionError("Operation does not belong to this tenant room")
        self._operations.setdefault(operation.operation_id, operation)

    def snapshot(self) -> tuple[StrokeOperation, ...]:
        return tuple(self._operations.values())


def measure_append_latency(canvas: CollaborativeCanvas, operations: list[StrokeOperation]) -> list[float]:
    latencies = []
    for operation in operations:
        started = perf_counter()
        canvas.append(operation)
        latencies.append((perf_counter() - started) * 1000)
    return latencies
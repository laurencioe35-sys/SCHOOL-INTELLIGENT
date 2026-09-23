from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AiCostMode(StrEnum):
    THROTTLE = "THROTTLE"
    MANUAL_ONLY = "MANUAL_ONLY"
    DISABLED = "DISABLED"


@dataclass
class AiCostCircuitBreaker:
    throttle_limit: int = 80
    manual_only_limit: int = 100
    calls: int = 0

    @property
    def mode(self) -> AiCostMode:
        if self.calls >= self.manual_only_limit:
            return AiCostMode.DISABLED
        if self.calls >= self.throttle_limit:
            return AiCostMode.MANUAL_ONLY
        return AiCostMode.THROTTLE

    def record_call(self) -> AiCostMode:
        self.calls += 1
        return self.mode
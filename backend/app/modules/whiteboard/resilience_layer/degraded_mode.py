from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DegradedMode(StrEnum):
    ONLINE_FULL = "ONLINE_FULL"
    DEGRADED_NO_AI = "DEGRADED_NO_AI"
    DEGRADED_LOCAL_ONLY = "DEGRADED_LOCAL_ONLY"


@dataclass
class DegradedModeManager:
    mode: DegradedMode = DegradedMode.ONLINE_FULL

    def can_write_freehand(self) -> bool:
        return True

    def on_connection_lost(self) -> None:
        self.mode = DegradedMode.DEGRADED_LOCAL_ONLY

    def on_ai_unavailable(self) -> None:
        if self.mode == DegradedMode.ONLINE_FULL:
            self.mode = DegradedMode.DEGRADED_NO_AI

    def on_reconnected(self, ai_available: bool = True) -> None:
        self.mode = DegradedMode.ONLINE_FULL if ai_available else DegradedMode.DEGRADED_NO_AI
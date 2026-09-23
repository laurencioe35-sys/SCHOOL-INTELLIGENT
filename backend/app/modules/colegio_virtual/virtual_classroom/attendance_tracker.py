from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PresenceSignal:
    student_id: str
    connected_minutes: float
    interaction_events: int


MIN_CONNECTED_RATIO = 0.8
MIN_INTERACTION_EVENTS = 1


def determine_attendance(signal: PresenceSignal, class_duration_minutes: float) -> str:
    if class_duration_minutes <= 0:
        raise ValueError("Class duration must be positive")
    connected_ratio = signal.connected_minutes / class_duration_minutes
    if connected_ratio >= MIN_CONNECTED_RATIO and signal.interaction_events >= MIN_INTERACTION_EVENTS:
        return "PRESENT"
    if connected_ratio >= MIN_CONNECTED_RATIO:
        return "PRESENT_PASSIVE"
    if connected_ratio > 0:
        return "PARTIAL"
    return "ABSENT"
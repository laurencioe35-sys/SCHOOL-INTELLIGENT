from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VideoParticipant:
    participant_id: str
    role: str


class LiveKitVideoBridge:
    provider = "livekit"

    def join_permissions(self, participant: VideoParticipant) -> dict[str, bool]:
        is_teacher = participant.role == "teacher"
        return {"publish": True, "mute_others": is_teacher, "remove_participants": is_teacher}


@dataclass(frozen=True)
class ReconnectionNotice:
    reconnect_required: bool
    missed_minutes: float
    recording_url: str | None
    message: str


def handle_live_disconnect(missed_minutes: float, recording_url: str | None) -> ReconnectionNotice:
    return ReconnectionNotice(
        reconnect_required=True,
        missed_minutes=missed_minutes,
        recording_url=recording_url,
        message=f"Te perdiste los últimos {missed_minutes:g} minutos; reconéctate y revisa la grabación disponible.",
    )
import pytest

from app.modules.colegio_virtual.virtual_classroom.attendance_tracker import (
    PresenceSignal,
    determine_attendance,
)
from app.modules.colegio_virtual.virtual_classroom.live_video_bridge import (
    LiveKitVideoBridge,
    VideoParticipant,
    handle_live_disconnect,
)
from app.modules.colegio_virtual.virtual_classroom.models import LiveClassSession
from app.modules.colegio_virtual.virtual_classroom.whiteboard_connector import (
    attach_whiteboard_to_class_session,
    detach_whiteboard_from_class_session,
)


def test_connected_without_interaction_is_passive_presence():
    signal = PresenceSignal("student-1", connected_minutes=85, interaction_events=0)
    assert determine_attendance(signal, 100) == "PRESENT_PASSIVE"


def test_live_disconnect_requires_reconnection_and_recording():
    notice = handle_live_disconnect(4, "https://recordings/class-1")
    assert notice.reconnect_required is True
    assert notice.recording_url
    assert "grabación" in notice.message


def test_teacher_has_livekit_moderation_permissions():
    permissions = LiveKitVideoBridge().join_permissions(VideoParticipant("teacher-1", "teacher"))
    assert permissions["mute_others"] is True
    assert permissions["remove_participants"] is True


@pytest.mark.asyncio
async def test_whiteboard_room_attaches_and_detaches_without_reimplementing_crdt():
    session = LiveClassSession("class-1", "teacher-1")
    assert await attach_whiteboard_to_class_session(session) == "class.class-1"
    await detach_whiteboard_from_class_session(session)
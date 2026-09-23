import pytest

from app.modules.whiteboard.recording_replay.lesson_events import LessonEventLog


def test_replay_keeps_stroke_and_audio_on_same_clock():
    log = LessonEventLog()
    log.append(tenant_id="tenant-1", lesson_id="lesson-1", event_type="stroke", t_offset_ms=100, payload={"x": 1})
    log.append(tenant_id="tenant-1", lesson_id="lesson-1", event_type="audio_transcript", t_offset_ms=100, payload={"text": "Hola"})
    timeline = log.timeline("tenant-1", "lesson-1")
    assert [event.t_offset_ms for event in timeline] == [100, 100]
    assert {event.event_type for event in timeline} == {"stroke", "audio_transcript"}


def test_lesson_events_are_append_only_and_tenant_scoped():
    log = LessonEventLog()
    event = log.append(tenant_id="tenant-1", lesson_id="lesson-1", event_type="stroke", t_offset_ms=1, payload={})
    assert log.timeline("tenant-2", "lesson-1") == ()
    with pytest.raises(PermissionError):
        log.update(event.event_id, payload={})
    with pytest.raises(PermissionError):
        log.delete(event.event_id)
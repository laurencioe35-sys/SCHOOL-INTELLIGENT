from uuid import uuid4

from app.db import SessionLocal, engine
from app.migrations import upgrade
from app.modules.whiteboard.recording_replay.repository import append_lesson_event, list_lesson_events


def test_lesson_events_persist_and_are_tenant_scoped():
    upgrade(engine)
    tenant_a, tenant_b = uuid4(), uuid4()
    with SessionLocal() as db:
        append_lesson_event(db, tenant_id=tenant_a, lesson_id="lesson-1", event_type="stroke", t_offset_ms=10, payload={"x": 1})
        append_lesson_event(
            db,
            tenant_id=tenant_b,
            lesson_id="lesson-1",
            event_type="audio_transcript",
            t_offset_ms=10,
            payload={"text": "hidden"},
        )
        assert len(list_lesson_events(db, tenant_id=tenant_a, lesson_id="lesson-1")) == 1
        assert list_lesson_events(db, tenant_id=tenant_b, lesson_id="lesson-1")[0].payload == '{"text": "hidden"}'
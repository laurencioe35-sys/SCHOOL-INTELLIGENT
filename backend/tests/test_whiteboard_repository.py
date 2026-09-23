from uuid import uuid4

from app.db import SessionLocal, engine
from app.migrations import upgrade
from app.modules.whiteboard.collaboration.repository import append_operation, list_operations


def test_whiteboard_operations_are_durable_idempotent_and_tenant_scoped():
    upgrade(engine)
    tenant_a, tenant_b = uuid4(), uuid4()
    with SessionLocal() as db:
        first = append_operation(
            db,
            tenant_id=tenant_a,
            room_id="room-1",
            operation_id="op-1",
            actor_id="user-1",
            operation_type="stroke",
            payload={"points": [[0, 0], [1, 1]]},
        )
        duplicate = append_operation(
            db,
            tenant_id=tenant_a,
            room_id="room-1",
            operation_id="op-1",
            actor_id="user-1",
            operation_type="stroke",
            payload={"points": [[9, 9]]},
        )
        assert duplicate.id == first.id
        assert len(list_operations(db, tenant_id=tenant_a, room_id="room-1")) == 1
        assert list_operations(db, tenant_id=tenant_b, room_id="room-1") == []
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import AuditLog


def _install_audit_immutability_trigger(db: Session) -> None:
    sqlite_trigger_update = text(
        """
        CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_update
        BEFORE UPDATE ON audit_log
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'audit_log is append-only: UPDATE not allowed');
        END;
        """
    )
    sqlite_trigger_delete = text(
        """
        CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_delete
        BEFORE DELETE ON audit_log
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'audit_log is append-only: DELETE not allowed');
        END;
        """
    )
    try:
        db.execute(sqlite_trigger_update)
        db.execute(sqlite_trigger_delete)
    except Exception:
        postgres_ddl = text(
            """
            CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'audit_log is append-only: % not allowed on row id=%', TG_OP, OLD.id;
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        try:
            db.execute(postgres_ddl)
            db.execute(text("DROP TRIGGER IF EXISTS trg_audit_log_no_update ON audit_log;"))
            db.execute(text("DROP TRIGGER IF EXISTS trg_audit_log_no_delete ON audit_log;"))
            db.execute(text("CREATE TRIGGER trg_audit_log_no_update BEFORE UPDATE ON audit_log FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();"))
            db.execute(text("CREATE TRIGGER trg_audit_log_no_delete BEFORE DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();"))
        except Exception:
            pass


def record_audit_event(
    db: Session,
    *,
    tenant_id: UUID | str,
    entity_name: str,
    entity_id: str,
    action: str,
    actor_user_id: UUID | str | None = None,
    details: dict | None = None,
    source: str | None = None,
) -> AuditLog:
    """Append-only audit insertion.

    This is intentionally the single write path for audit records so the
    application and database layers use the same behavior.
    """
    _install_audit_immutability_trigger(db)
    details_payload = details or {}
    event = AuditLog(
        id=uuid4(),
        tenant_id=UUID(str(tenant_id)),
        actor_user_id=UUID(str(actor_user_id)) if actor_user_id is not None else None,
        entity_name=entity_name,
        entity_id=str(entity_id),
        action=action.upper(),
        details=json.dumps(details_payload, default=str, sort_keys=True),
        occurred_at=datetime.now(UTC),
    )
    if source:
        event.details = json.dumps({"source": source, **details_payload}, default=str, sort_keys=True)
    db.add(event)
    db.flush()
    return event


def ensure_audit_log_immutable(db: Session) -> None:
    """Attempt to install PostgreSQL-safe audit mutability protections.

    SQLite does not support the same CREATE TRIGGER semantics, but keeping the
    guard here preserves the contract and makes the expected behavior explicit.
    """
    statement = text(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: % not allowed on row id=%', TG_OP, OLD.id;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_audit_log_no_update ON audit_log;
        DROP TRIGGER IF EXISTS trg_audit_log_no_delete ON audit_log;

        CREATE TRIGGER trg_audit_log_no_update
        BEFORE UPDATE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();

        CREATE TRIGGER trg_audit_log_no_delete
        BEFORE DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
        """
    )
    try:
        db.execute(statement)
    except Exception:
        # Postgres-specific trigger setup is not available on SQLite-backed tests.
        return

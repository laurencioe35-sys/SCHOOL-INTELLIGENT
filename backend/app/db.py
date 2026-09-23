import re
from collections.abc import Generator
from contextvars import ContextVar

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import get_settings

settings = get_settings()
if settings.database_url.startswith("sqlite"):
    engine: Engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        pool_pre_ping=True,
    )
else:
    engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
_current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)


@event.listens_for(engine, "before_cursor_execute")
def _block_audit_mutation(conn, cursor, statement, parameters, context, executemany):
    normalized = re.sub(r"\s+", " ", statement.strip()).upper()
    if re.match(r"^(UPDATE|DELETE)\s+.*\bAUDIT_LOG\b", normalized):
        raise PermissionError("audit_log is append-only: UPDATE/DELETE not allowed")
    return statement, parameters


class Base(DeclarativeBase):
    pass


def initialize_db() -> None:
    from .migrations import upgrade

    upgrade(engine)


# Tests and scripts can use SessionLocal directly without importing the API app.
initialize_db()


def set_current_tenant_id(tenant_id: str | None) -> None:
    _current_tenant_id.set(str(tenant_id) if tenant_id is not None else None)


def get_current_tenant_id() -> str | None:
    return _current_tenant_id.get()


def clear_current_tenant_id() -> None:
    _current_tenant_id.set(None)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        tenant_id = get_current_tenant_id()
        if tenant_id:
            session.info["tenant_id"] = tenant_id
        yield session

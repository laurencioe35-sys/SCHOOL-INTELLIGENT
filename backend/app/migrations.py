from __future__ import annotations

from sqlalchemy import Column, Integer, MetaData, String, Table, insert, inspect, select
from sqlalchemy.engine import Engine

from .db import Base

SCHEMA_VERSION = 12


def _schema_versions_table(metadata: MetaData) -> Table:
    return Table(
        "schema_versions",
        metadata,
        Column("version", Integer, primary_key=True),
        Column("description", String(200), nullable=False),
        extend_existing=True,
    )


def upgrade(engine: Engine) -> int:
    """Apply the current metadata and record a reproducible schema version."""
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    versions = _schema_versions_table(Base.metadata)
    versions.create(bind=engine, checkfirst=True)
    with engine.begin() as connection:
        existing = connection.scalar(select(versions.c.version).order_by(versions.c.version.desc()).limit(1))
        if existing is None:
            connection.execute(
                insert(versions).values(version=SCHEMA_VERSION, description="ERP, payments, live classroom, credentials, proctoring, content library, gradebook, and whiteboard schema")
            )
        elif existing < SCHEMA_VERSION:
            connection.execute(
                insert(versions).values(version=SCHEMA_VERSION, description="Current ERP, payments, live classroom, credentials, proctoring, content library, gradebook, and whiteboard schema")
            )
    return SCHEMA_VERSION


def current_version(engine: Engine) -> int:
    versions = _schema_versions_table(Base.metadata)
    if not inspect(engine).has_table("schema_versions"):
        return 0
    with engine.connect() as connection:
        return int(connection.scalar(select(versions.c.version).order_by(versions.c.version.desc()).limit(1)) or 0)

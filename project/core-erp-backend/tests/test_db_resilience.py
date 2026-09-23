"""
Tests de resiliencia de conexión a Postgres.

No son mocks de "simular que falla" — usan una URL de Postgres real que
apunta a un puerto donde efectivamente NO hay nada escuchando
(127.0.0.1:59999), para que OperationalError sea el error real de
psycopg2 al no poder conectar, igual que vería el proceso en producción
si Postgres estuviera caído.
"""
import time

import pytest
from sqlalchemy.exc import OperationalError

from database.connection import _create_engine_with_retry, get_db_read, SessionLocal
from sqlalchemy import text

UNREACHABLE_URL = "postgresql+psycopg2://postgres:postgres@127.0.0.1:59999/nope"
REAL_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/erp_educativo_test"


def test_create_engine_with_retry_succeeds_against_real_postgres():
    engine = _create_engine_with_retry(REAL_URL, max_attempts=1)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
    assert result == 1
    engine.dispose()


def test_create_engine_with_retry_raises_after_exhausting_attempts_against_unreachable_host():
    """max_attempts=1 para no alargar el test con esperas reales — lo que
    se prueba es que SÍ propaga el error real (no lo traga en silencio),
    no la duración exacta del backoff."""
    with pytest.raises(OperationalError):
        _create_engine_with_retry(UNREACHABLE_URL, max_attempts=1, base_delay_seconds=0.01)


def test_create_engine_with_retry_actually_retries_multiple_times():
    """Verifica el backoff de verdad: cuenta cuánto tarda con
    max_attempts=3 y delays mínimos — debe tomar al menos
    0.01 + 0.02 = 0.03s (dos esperas entre 3 intentos), probando que el
    retry no es un no-op."""
    start = time.monotonic()
    with pytest.raises(OperationalError):
        _create_engine_with_retry(UNREACHABLE_URL, max_attempts=3, base_delay_seconds=0.01)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.03


def test_get_db_read_falls_back_to_primary_when_no_replica_configured():
    """Sin ERP_DATABASE_URL_REPLICA (caso normal en este sandbox), debe
    devolver una sesión funcional contra la primaria, sin lanzar."""
    gen = get_db_read()
    db = next(gen)
    try:
        result = db.execute(text("SELECT 1")).scalar()
        assert result == 1
    finally:
        gen.close()


def test_get_db_read_uses_configured_replica_when_available(monkeypatch):
    """Contra la réplica de streaming REAL montada en este sandbox
    (ver scripts/setup_read_replica.sh, puerto 5433) — no un mock. Se
    confirma con pg_is_in_recovery(): True significa "esta sesión de
    verdad está sirviendo desde el standby", no solo desde cualquier
    Postgres que responda.

    Se salta automáticamente si la réplica no está corriendo en este
    momento del sandbox (por ejemplo, si el proceso se reinició) — el
    resto de la suite no depende de que la réplica esté viva."""
    replica_url = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5433/erp_educativo_test"
    import database.connection as conn_module
    from sqlalchemy.orm import sessionmaker

    try:
        probe_engine = conn_module.create_engine(replica_url, pool_pre_ping=True)
        with probe_engine.connect() as c:
            c.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("réplica de streaming (puerto 5433) no está corriendo en este momento del sandbox")

    monkeypatch.setattr(conn_module, "_ReplicaSessionLocal", sessionmaker(bind=probe_engine))

    gen = conn_module.get_db_read()
    db = next(gen)
    try:
        in_recovery = db.execute(text("SELECT pg_is_in_recovery()")).scalar()
        assert in_recovery is True, "la sesión debería venir del standby, que siempre reporta pg_is_in_recovery()=true"
    finally:
        gen.close()
    probe_engine.dispose()


def test_get_db_read_falls_back_to_primary_when_replica_url_is_unreachable(monkeypatch):
    """Simula una réplica configurada pero caída: apunta
    _ReplicaSessionLocal a un engine que no puede conectar, y confirma
    que get_db_read() NO propaga el error — cae a la primaria y sigue
    sirviendo la request."""
    import database.connection as conn_module
    from sqlalchemy.orm import sessionmaker

    broken_engine = conn_module.create_engine(UNREACHABLE_URL, pool_pre_ping=False)
    broken_session_factory = sessionmaker(bind=broken_engine)

    monkeypatch.setattr(conn_module, "_ReplicaSessionLocal", broken_session_factory)

    gen = conn_module.get_db_read()
    db = next(gen)
    try:
        result = db.execute(text("SELECT 1")).scalar()
        assert result == 1  # se sirvió desde la PRIMARIA, no desde la réplica rota
    finally:
        gen.close()
    broken_engine.dispose()

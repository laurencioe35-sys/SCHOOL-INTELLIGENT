"""
Pool de conexiones.

Antes: sqlite:///./erp.db (solo para pruebas rápidas de un único proceso).
Ahora: PostgreSQL real, probado en este mismo entorno (ver README de
migraciones). SQLite ya no es el default porque no soporta bien
escrituras concurrentes — exactamente el caso de 40 alumnos entregando
notas al mismo tiempo que motivó todo este rediseño.

Postgres como punto único de falla (nuevo): hasta esta sesión, si la
única instancia de Postgres se caía, TODO el ERP dejaba de responder —
tanto lecturas como escrituras — sin ningún mecanismo de degradación.
Este módulo agrega tres piezas, cada una probada en este entorno con
Postgres real (ver tests/test_db_resilience.py):

  1. **pool_pre_ping**: cada conexión se verifica con un `SELECT 1`
     barato antes de reusarla del pool. Sin esto, una conexión que
     Postgres cerró silenciosamente (por un reinicio o un firewall/NAT
     con timeout de idle) fallaba con un error críptico en medio de una
     request real, en vez de reconectar de forma transparente.
  2. **Retry con backoff exponencial al crear el engine**: si Postgres
     todavía no aceptó conexiones cuando arranca el proceso (carrera de
     arranque típica en `docker compose up`, donde el contenedor de la
     app puede arrancar antes de que Postgres termine su
     inicialización), se reintenta varias veces en vez de que el proceso
     completo crashee con un traceback de conexión rechazada.
  3. **Réplica de lectura opcional con fallback automático**: si se
     define `ERP_DATABASE_URL_REPLICA` (una instancia en streaming
     replication desde la primaria — ver
     `scripts/setup_read_replica.sh`, ejecutado y verificado de verdad en
     este sandbox), los endpoints de solo lectura pueden usar
     `get_db_read()` en vez de `get_db()`. Si la réplica no responde,
     `get_db_read()` cae automáticamente a la primaria (logueando la
     degradación) en vez de tumbar la petición — la primaria absorbe la
     carga extra en vez de que el usuario vea un error.

**Lo que esto NO resuelve** (fuera de alcance de esta sesión, ver
README): no hay failover automático de la primaria (si la primaria en sí
se cae, las ESCRITURAS siguen sin funcionar hasta promover manualmente la
réplica a primaria — eso requiere un orquestador como Patroni/repmgr, no
solo SQLAlchemy) — lo que se gana aquí es que las LECTURAS pueden
sobrevivir la caída de la réplica (fallback a primaria) y que blips
transitorios de red ya no tumban conexiones del pool silenciosamente.
"""
import os
import time
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from database.models import Base

logger = logging.getLogger("erp.database")

DATABASE_URL = os.getenv(
    "ERP_DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/erp_educativo",
)
REPLICA_DATABASE_URL = os.getenv("ERP_DATABASE_URL_REPLICA")  # opcional, no configurado por defecto


def _create_engine_with_retry(url: str, *, max_attempts: int = 5, base_delay_seconds: float = 0.5):
    """Crea el engine y prueba una conexión real, reintentando con
    backoff exponencial (0.5s, 1s, 2s, 4s, ...) si Postgres todavía no
    acepta conexiones. `max_attempts=1` (usado en tests) desactiva el
    retry para no alargar la suite con esperas reales cuando lo que se
    prueba es justamente el caso "nunca se recupera"."""
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(
        url,
        connect_args=connect_args,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # valida la conexión con SELECT 1 antes de reusarla del pool
    )

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine
        except OperationalError as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            delay = base_delay_seconds * (2 ** (attempt - 1))
            logger.warning(
                "db_connect_retry attempt=%d/%d delay_seconds=%.1f error=%s",
                attempt, max_attempts, delay, exc,
            )
            time.sleep(delay)

    raise last_error


engine = _create_engine_with_retry(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Engine de réplica: solo se crea si ERP_DATABASE_URL_REPLICA está
# definida. A diferencia del engine primario, NO reintenta al arrancar
# ni tumba el proceso si la réplica no está disponible — es opcional por
# diseño, así que su ausencia (o caída) nunca debe impedir que el ERP
# arranque o sirva tráfico con la primaria sola.
_replica_engine = None
_ReplicaSessionLocal = None
if REPLICA_DATABASE_URL:
    _replica_engine = create_engine(REPLICA_DATABASE_URL, pool_size=5, max_overflow=10, pool_pre_ping=True)
    _ReplicaSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_replica_engine)


def init_db():
    """Solo para entornos de desarrollo rápido / tests. En producción real
    el esquema se crea y actualiza con Alembic (`alembic upgrade head`),
    nunca con create_all — ver alembic/README dentro de esta carpeta."""
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_read():
    """Dependency para endpoints de SOLO LECTURA. Si hay una réplica
    configurada Y responde, la usa (quita carga de lectura de la
    primaria); si no hay réplica configurada, o si está configurada pero
    no responde, cae a la primaria de forma transparente para quien
    llama — nunca lanza una excepción distinta a las que ya lanzaría
    get_db() con la primaria caída.

    IMPORTANTE: los endpoints que usan esta dependency NO deben escribir
    en la sesión que reciben — una réplica de streaming replication es de
    solo lectura a nivel de Postgres, así que un INSERT/UPDATE contra
    ella fallaría en producción real aunque en este sandbox la "réplica"
    de prueba comparta el mismo Postgres físico (ver
    scripts/setup_read_replica.sh) y técnicamente lo permita.
    """
    if _ReplicaSessionLocal is not None:
        try:
            db = _ReplicaSessionLocal()
            db.execute(text("SELECT 1"))
            try:
                yield db
            finally:
                db.close()
            return
        except OperationalError as exc:
            logger.warning("db_read_replica_unavailable falling_back_to_primary error=%s", exc)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

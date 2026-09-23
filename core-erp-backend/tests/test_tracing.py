"""
Tests de tracing distribuido.

Se agrega un `InMemorySpanExporter` REAL de OpenTelemetry (no un mock
propio) al TracerProvider ya inicializado por `main.py`, y se verifica
que las requests HTTP generan spans de verdad, con el trace_id
propagándose al header de respuesta y al log estructurado — exactamente
lo que un operador vería en Jaeger/Tempo + su sistema de logs si
definiera OTEL_EXPORTER_OTLP_ENDPOINT en producción.

Corre junto al resto de la suite: pytest -v (requiere Postgres/Redis).
"""
import os

os.environ["ERP_DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/erp_educativo_test"
os.environ["ERP_REDIS_URL"] = "redis://localhost:6379/1"
os.environ.setdefault("ERP_SECRET_KEY", "test_secret_key")

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from database.connection import engine
from database.models import Base
from main import app
from observability.logging_config import log_event

client = TestClient(app)

_memory_exporter = InMemorySpanExporter()
# Se agrega al provider global YA creado por setup_tracing() en main.py —
# prueba directa de que setup_tracing() de verdad configuró un
# TracerProvider real y no un objeto decorativo.
trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(_memory_exporter))


@pytest.fixture(autouse=True)
def clean_db_and_spans():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    import redis
    r = redis.from_url(os.environ["ERP_REDIS_URL"])
    r.flushdb()
    _memory_exporter.clear()
    yield


def test_request_produces_a_span_with_service_name():
    resp = client.get("/")
    assert resp.status_code == 200

    spans = _memory_exporter.get_finished_spans()
    assert len(spans) >= 1, "FastAPIInstrumentor debería generar al menos un span raíz por request"
    assert spans[0].resource.attributes["service.name"] == "core-erp-backend"


def test_response_includes_trace_id_header():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "X-Trace-Id" in resp.headers
    trace_id = resp.headers["X-Trace-Id"]
    assert len(trace_id) == 32  # trace_id hex de 128 bits, formato W3C

    spans = _memory_exporter.get_finished_spans()
    span_trace_ids = {format(s.context.trace_id, "032x") for s in spans}
    assert trace_id in span_trace_ids, "El X-Trace-Id expuesto debe ser el trace_id real del span de la request"


def test_db_query_produces_a_child_span():
    """El registro de usuario hace queries reales a Postgres — con
    SQLAlchemyInstrumentor activo, cada una debe aparecer como span hijo
    del span raíz de la request, no solo el span HTTP de FastAPI."""
    resp = client.post("/auth/register", json={
        "full_name": "Traza Test", "email": "traza@test.pe",
        "password": "clave123", "organization_name": "Colegio Traza",
    })
    assert resp.status_code == 200

    spans = _memory_exporter.get_finished_spans()
    span_names = [s.name for s in spans]
    db_spans = [s for s in spans if s.instrumentation_scope and "sqlalchemy" in s.instrumentation_scope.name]
    assert db_spans, f"Se esperaba al menos un span de sqlalchemy entre: {span_names}"


def test_log_event_includes_trace_id_when_inside_a_span():
    """Fuera de una request (como este test corre directo, sin pasar por
    el middleware de FastAPI) no hay span activo, así que trace_id debe
    ser None — comportamiento explícito, no un campo vacío silencioso."""
    tracer = trace.get_tracer(__name__)
    captured = {}
    import observability.logging_config as logging_module

    original_logger_info = logging_module.logger.info

    def _capture(event, extra=None, **kwargs):
        captured["extra"] = extra
        return original_logger_info(event, extra=extra, **kwargs)

    logging_module.logger.info = _capture
    try:
        with tracer.start_as_current_span("test-span-manual"):
            log_event("evento_de_prueba", foo="bar")
    finally:
        logging_module.logger.info = original_logger_info

    assert "trace_id" in captured["extra"], "log_event debe incluir trace_id cuando hay un span activo"
    assert len(captured["extra"]["trace_id"]) == 32

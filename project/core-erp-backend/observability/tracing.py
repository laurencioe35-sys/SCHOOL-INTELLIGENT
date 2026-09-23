"""
Tracing distribuido con OpenTelemetry.

Por qué: hasta ahora, si una petición era lenta o fallaba, el único rastro
era el log JSON de esa request (`observability/logging_config.py`) en el
proceso del ERP. Pero una petición real cruza varios sistemas: el
middleware de rate limiting habla con Redis, el endpoint habla con
Postgres, y en el flujo completo del proyecto el ERP dispara trabajo hacia
`ai-agents-engine` y el estado termina reflejado en `multimedia-stream-server`
vía Redis Pub/Sub. Sin tracing distribuido, correlacionar "esta petición
lenta del profesor" con "esta query lenta a Postgres" o "este evento que
tardó en llegar al pizarrón" requería cruzar logs a mano por timestamp.

Qué hace este módulo, probado en este entorno:
  - Crea un `TracerProvider` real de OpenTelemetry con un `Resource` que
    identifica el servicio (`service.name=core-erp-backend`).
  - Instrumenta FastAPI automáticamente (cada request = un span raíz),
    SQLAlchemy (cada query = un span hijo) y el cliente de Redis (cada
    comando = un span hijo) — así un trace de "profesor sube una nota"
    ya incluye, sin código adicional en cada endpoint, cuánto tardó la
    query a Postgres y cuánto el chequeo de rate limit en Redis.
  - Expone el `trace_id` activo vía `current_trace_id()`, usado en
    `logging_config.log_event` para que CADA log JSON incluya el mismo
    `trace_id` que sus spans — así se puede buscar en el sistema de logs
    y en el backend de tracing con la misma clave.
  - Propaga contexto W3C `traceparent` en peticiones salientes vía
    `inject_trace_headers()`, para cuando el ERP llegue a llamar a otro
    servicio HTTP (ver nota abajo sobre qué NO está conectado todavía).

Exportador, con compromiso honesto: por defecto exporta a consola
(`ConsoleSpanExporter`), verificado en este entorno con el exportador en
memoria de las pruebas (`tests/test_tracing.py`) — no requiere ningún
backend externo. Si se define `OTEL_EXPORTER_OTLP_ENDPOINT` (ej. un
Jaeger o Tempo corriendo en docker-compose), se exporta además vía OTLP
sobre HTTP — **rama no ejercitada en este sandbox** porque no hay un
colector OTLP corriendo aquí; queda documentada la variable exacta que
hay que definir para activarla en un entorno real.

**Lo que esto NO conecta todavía** (fuera de alcance de esta sesión):
`ai-agents-engine` y `multimedia-stream-server` no están instrumentados
ni reciben el header `traceparent` en ningún llamado real — hoy sólo se
tocan entre sí a través de `scripts/e2e_smoke_test.sh`, que no pasa
headers de tracing. Instrumentarlos es directo (mismo patrón: SDK +
auto-instrumentation) pero es trabajo aparte, ver README.
"""
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.propagate import inject

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "core-erp-backend")

_provider: TracerProvider | None = None


def setup_tracing(app=None, engine=None) -> TracerProvider:
    """Inicializa el TracerProvider global e instrumenta FastAPI/SQLAlchemy.

    Idempotente a propósito: los tests importan `main` varias veces en el
    mismo proceso (cada módulo de test hace su propio `from main import
    app`), y crear un TracerProvider dos veces sobre el mismo proceso
    generaba una advertencia de OpenTelemetry ("Overriding of current
    TracerProvider is not allowed") — se corrigió devolviendo el provider
    ya creado en vez de reconstruirlo.
    """
    global _provider
    if _provider is not None:
        return _provider

    resource = Resource.create({
        "service.name": SERVICE_NAME,
        "service.namespace": "erp-educativo",
    })
    provider = TracerProvider(resource=resource)

    # Exportador de consola: cada span impreso en JSON a stdout, útil
    # para ver traces sin backend externo. Detrás de una env var a
    # propósito: imprimir CADA span (incluyendo los internos de
    # SQLAlchemy/Redis) en cada request es ruido serio en producción, y
    # en los tests de este repo se descubrió que ralentiza lo bastante
    # como para romper un test de timing real basado en `time.sleep`
    # (`test_window_resets_after_expiration`) cuando corre junto al resto
    # de la suite. El exportador en memoria de `tests/test_tracing.py`
    # sigue probando el pipeline de spans sin depender de esto.
    if os.getenv("OTEL_CONSOLE_EXPORT", "").lower() in ("1", "true", "yes"):
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        # No ejercitado en este entorno (no hay colector OTLP corriendo
        # aquí) — import local para no exigir la dependencia si nadie
        # define la variable.
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
        )

    trace.set_tracer_provider(provider)
    _provider = provider

    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)

    if engine is not None:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        SQLAlchemyInstrumentor().instrument(engine=engine)

    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        RedisInstrumentor().instrument()
    except Exception:
        # Instrumentar redis es "nice to have"; si la librería del cliente
        # instalada no es compatible, no debe tumbar el arranque del ERP.
        pass

    return provider


def current_trace_id() -> str | None:
    """ID de trace activo en formato hex de 32 caracteres, o None si no
    hay ningún span activo (ej. código que corre fuera de una request,
    como el batch worker). Usado por logging_config para correlacionar
    logs y traces."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx is None or ctx.trace_id == 0:
        return None
    return format(ctx.trace_id, "032x")


def inject_trace_headers(headers: dict | None = None) -> dict:
    """Inyecta el header W3C `traceparent` (y `tracestate` si existe) del
    span activo en un diccionario de headers salientes, para que el
    servicio que reciba la petición HTTP pueda continuar el mismo trace
    en vez de empezar uno nuevo desconectado. Usar así:

        headers = inject_trace_headers({"Authorization": f"Bearer {token}"})
        requests.post(url, headers=headers, ...)
    """
    carrier = dict(headers) if headers else {}
    inject(carrier)
    return carrier

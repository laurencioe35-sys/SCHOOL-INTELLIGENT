"""
Logging estructurado en JSON.

Por qué: hoy (antes de este cambio) el único rastro de lo que pasa en
producción son los logs de acceso por defecto de uvicorn ("GET / 200 OK"),
que no dicen QUÉ usuario hizo QUÉ, ni permiten filtrar/alertar en un
sistema real de logs (Datadog, CloudWatch, Loki, etc.) sin parsear texto
libre. Con logging JSON estructurado, cada línea es un evento con campos
consistentes (`event`, `user_id`, `classroom_id`, etc.) que cualquier
sistema de logs puede indexar y filtrar directamente.
"""
import logging
import sys

from pythonjsonlogger import jsonlogger

logger = logging.getLogger("erp")
logger.setLevel(logging.INFO)

_handler = logging.StreamHandler(sys.stdout)
_formatter = jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
    rename_fields={"asctime": "timestamp", "levelname": "level"},
)
_handler.setFormatter(_formatter)
logger.addHandler(_handler)
logger.propagate = False


def log_event(event: str, **fields):
    """Emite un log estructurado de un evento de negocio.

    Uso: log_event("grade_submitted", user_id=user.id, classroom_id=classroom_id, score=score)
    Esto produce una línea JSON como:
    {"timestamp": "...", "level": "INFO", "name": "erp", "message": "grade_submitted",
     "user_id": "...", "classroom_id": "...", "score": 18, "trace_id": "..."}

    trace_id (nuevo): si hay un span de OpenTelemetry activo (o sea, este
    log ocurre dentro de una request HTTP ya instrumentada por
    `observability/tracing.py`), se agrega automáticamente para poder
    buscar "todos los logs de este trace" en el sistema de logs con la
    misma clave que usa el backend de tracing. Import diferido a
    propósito: así este módulo no depende de que `tracing` esté
    inicializado (o incluso instalado) para poder loguear.
    """
    try:
        from observability.tracing import current_trace_id
        trace_id = current_trace_id()
    except Exception:
        trace_id = None
    if trace_id:
        fields = {**fields, "trace_id": trace_id}
    logger.info(event, extra=fields)

"""
Métricas Prometheus.

Expone /metrics con contadores y latencias reales de: requests HTTP,
notas consolidadas por el batch worker, y eventos en dead-letter — que
son justo las señales que necesitarías para poner una alerta real
("si dead_letter_total sube, algo está mandando datos corruptos").
"""
from prometheus_client import Counter, Histogram, CONTENT_TYPE_LATEST, generate_latest

http_requests_total = Counter(
    "erp_http_requests_total", "Total de requests HTTP", ["method", "path", "status_code"]
)
http_request_duration_seconds = Histogram(
    "erp_http_request_duration_seconds", "Duración de requests HTTP", ["method", "path"]
)
grades_consolidated_total = Counter(
    "erp_grades_consolidated_total", "Total de notas consolidadas por el batch worker"
)
grades_dead_letter_total = Counter(
    "erp_grades_dead_letter_total", "Total de notas movidas a la cola dead-letter"
)
rate_limit_exceeded_total = Counter(
    "erp_rate_limit_exceeded_total", "Total de peticiones rechazadas por exceder el límite de tasa", ["scope"]
)


def metrics_response() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST

"""
Dead-letter queue del loop de agentes — NUEVO, no existía en el proyecto.

`AgentRegistry.run_all` ya aislaba fallos de agentes individuales (uno
roto no tumba a los demás). Pero el pipeline BASE (context_agent ->
pedagogical_agent -> ui_compiler_agent en loop_engine.py) no tenía ese
mismo aislamiento: si `extract_semantic_chunk` lanzaba una excepción
(por ejemplo, el LLM real devuelve un JSON que no cumple `SemanticChunk`,
o un `raw_text` corrupto), esa excepción se propagaba fuera de
`process_one()` y `run_forever()` — el `while True` completo se caía y
dejaba de escuchar la cola. En un salón en vivo eso significa que UNA
frase rara del profesor apaga la pizarra interactiva para toda la clase.

`DeadLetterQueue` es donde ese evento problemático va a parar en vez de
tumbar el loop: se guarda el evento original, el motivo del fallo, un
timestamp y un contador de reintentos. El loop sigue vivo y sigue
atendiendo al resto de la clase con normalidad. Mismo patrón de
observabilidad que `grades_dead_letter_total` en
core-erp-backend/observability/metrics.py, portado aquí para el motor de
IA en tiempo real.

--- NUEVO: backend Redis --------------------------------------------
Igual que con el circuit breaker (ver registry.py), la versión en
memoria de esta cola solo sobrevive dentro de UN proceso: si tienes 2+
réplicas de ai-agents-engine detrás de la misma cola de entrada, cada
una acumula su propio dead-letter y un operador tendría que revisar N
lugares distintos para ver todos los eventos fallidos del sistema.
`RedisDeadLetterQueue` centraliza eso en una sola lista de Redis
compartida por todas las réplicas, para que "reintentar los eventos
fallidos" sea una sola operación (`pop_for_retry()`), no una por réplica.
Se ejercita de verdad en tests/test_resilience_redis.py contra un Redis
real; si Redis no está disponible, esos tests se saltan explícitamente.
"""
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeadLetterEntry:
    event: dict[str, Any]
    reason: str
    failed_at: float
    attempts: int = 1


class DeadLetterQueue:
    """Buffer en memoria de eventos que el pipeline base no pudo procesar.
    Se expone `all_entries()` y `pop_for_retry()` para que un proceso de
    reintento (o un endpoint de soporte para el profesor) pueda revisarlos
    y reencolarlos manualmente sin perder el evento original."""

    def __init__(self, clock=time.monotonic):
        self._entries: list[DeadLetterEntry] = []
        self._clock = clock

    def push(self, event: dict[str, Any], reason: str) -> DeadLetterEntry:
        entry = DeadLetterEntry(event=event, reason=reason, failed_at=self._clock())
        self._entries.append(entry)
        return entry

    def __len__(self) -> int:
        return len(self._entries)

    def all_entries(self) -> list[DeadLetterEntry]:
        return list(self._entries)

    def pop_for_retry(self) -> list[dict[str, Any]]:
        """Saca todos los eventos acumulados para reintentarlos (ej. desde
        un cron o un botón de 'reintentar' en el panel del profesor) y
        vacía la cola — quien llama es responsable de re-publicarlos en
        el event_queue."""
        events = [e.event for e in self._entries]
        self._entries.clear()
        return events


class RedisDeadLetterQueue:
    """Backend real con Redis (lista `RPUSH`/`LRANGE`), compartido entre
    todas las réplicas del motor. Usa `time.time()` (época UNIX) como
    reloj por defecto, no `time.monotonic()`: el timestamp se escribe en
    un proceso y puede leerse desde otro (ej. un endpoint de soporte
    corriendo en una réplica distinta), y monotonic() no es comparable
    entre procesos — mismo razonamiento que en RedisCircuitBreaker."""

    def __init__(self, redis_url: str, key: str = "agents:dead_letter", clock=time.time):
        import redis  # import local: no exige la dependencia en modo memoria

        self._r = redis.from_url(redis_url, decode_responses=True)
        self._key = key
        self._clock = clock

    def push(self, event: dict[str, Any], reason: str) -> DeadLetterEntry:
        entry = DeadLetterEntry(event=event, reason=reason, failed_at=self._clock())
        self._r.rpush(self._key, json.dumps({
            "event": entry.event, "reason": entry.reason,
            "failed_at": entry.failed_at, "attempts": entry.attempts,
        }))
        return entry

    def __len__(self) -> int:
        return self._r.llen(self._key)

    def all_entries(self) -> list[DeadLetterEntry]:
        raw = self._r.lrange(self._key, 0, -1)
        return [DeadLetterEntry(**json.loads(item)) for item in raw]

    def pop_for_retry(self) -> list[dict[str, Any]]:
        raw = self._r.lrange(self._key, 0, -1)
        events = [json.loads(item)["event"] for item in raw]
        self._r.delete(self._key)
        return events


def build_dead_letter_queue(redis_url: str | None = None, key: str = "agents:dead_letter", clock=None):
    """Factory: Redis si ERP_REDIS_URL está configurado (compartido entre
    réplicas), memoria de proceso si no — mismo patrón de fallback
    honesto que build_blackboard()/build_event_queue()/build_circuit_breaker()."""
    redis_url = redis_url if redis_url is not None else os.getenv("ERP_REDIS_URL")
    if redis_url:
        try:
            return RedisDeadLetterQueue(redis_url, key=key, clock=clock or time.time)
        except ImportError:
            pass  # sin el paquete redis instalado, cae a memoria
    return DeadLetterQueue(clock=clock or time.monotonic)

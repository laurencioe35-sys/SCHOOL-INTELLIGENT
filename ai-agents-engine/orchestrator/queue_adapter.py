"""
Cola de eventos que alimenta el loop de agentes.

Antes (main_agents.py): `process_chunk()` era una función pura que había
que llamar a mano, una vez, desde afuera (así la usa hoy
scripts/e2e_smoke_test.sh). Eso NO es un loop real: nadie está
"escuchando" nada de forma continua.

Ahora: `EventQueue` es un receptor real — algo (el transcriptor Whisper
del multimedia-stream-server, un test, una demo) empuja eventos con
`publish()`, y `AgentLoop` (en loop_engine.py) los consume en un loop
`while True` real, uno tras otro, sin que nadie tenga que volver a
invocar nada a mano por evento.

Mismo patrón de fallback honesto que queue.js: memoria por defecto,
Redis Streams si ERP_REDIS_URL está configurado (no ejercitado en este
sandbox, documentado igual que el resto del proyecto).
"""
import asyncio
import heapq
import os
from typing import Any, Optional


class InMemoryEventQueue:
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()

    async def publish(self, event: dict[str, Any]) -> None:
        await self._queue.put(event)

    async def consume(self) -> dict[str, Any]:
        """Bloquea hasta que haya un evento disponible — el corazón del loop."""
        return await self._queue.get()

    def qsize(self) -> int:
        return self._queue.qsize()


# --- NUEVO: cola con prioridad ------------------------------------------
# Un salón en vivo mezcla eventos muy distintos en urgencia: un fragmento
# de transcripción rutinario puede esperar unos milisegundos más, pero
# "un alumno pidió ayuda" o "el profesor marcó una emergencia pedagógica"
# no debería quedar detrás de 40 transcript_chunk acumulados en un pico de
# tráfico. InMemoryEventQueue (FIFO puro) no distingue eso. Esta variante
# sí, sin romper la interfaz publish()/consume()/qsize() que ya usa
# AgentLoop — se puede intercambiar una por otra sin tocar loop_engine.py.
PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


class PriorityEventQueue:
    """Cola con prioridad basada en heapq. Los eventos declaran su
    prioridad con event["priority"] (uno de PRIORITY_RANK); si no la
    declaran, se tratan como "normal". Dentro de la misma prioridad se
    respeta FIFO (se usa un contador de secuencia como desempate, igual
    que recomienda la documentación estándar de heapq para evitar tener
    que comparar los dicts de evento entre sí)."""

    def __init__(self):
        self._heap: list[tuple[int, int, dict[str, Any]]] = []
        self._counter = 0
        self._not_empty = asyncio.Condition()

    async def publish(self, event: dict[str, Any]) -> None:
        priority = PRIORITY_RANK.get(event.get("priority", "normal"), PRIORITY_RANK["normal"])
        async with self._not_empty:
            heapq.heappush(self._heap, (priority, self._counter, event))
            self._counter += 1
            self._not_empty.notify()

    async def consume(self) -> dict[str, Any]:
        async with self._not_empty:
            while not self._heap:
                await self._not_empty.wait()
            _, _, event = heapq.heappop(self._heap)
            return event

    def qsize(self) -> int:
        return len(self._heap)


class RedisStreamEventQueue:
    """Backend real con Redis Streams (XADD/XREAD), usado solo si
    ERP_REDIS_URL está configurado. No ejercitado en este sandbox por no
    haber un servidor Redis corriendo; el punto de integración queda
    documentado igual que en el resto del proyecto."""

    def __init__(self, redis_url: str, stream_name: str = "class:transcript:chunks"):
        import redis  # import local

        self._r = redis.from_url(redis_url, decode_responses=True)
        self._stream = stream_name
        self._last_id = "$"  # solo eventos nuevos desde que arranca el loop

    async def publish(self, event: dict[str, Any]) -> None:
        import json

        await asyncio.to_thread(self._r.xadd, self._stream, {"data": json.dumps(event)})

    async def consume(self) -> dict[str, Any]:
        import json

        def _blocking_read():
            resp = self._r.xread({self._stream: self._last_id}, block=0, count=1)
            _, entries = resp[0]
            entry_id, fields = entries[0]
            self._last_id = entry_id
            return json.loads(fields["data"])

        return await asyncio.to_thread(_blocking_read)

    def qsize(self) -> int:
        return self._r.xlen(self._stream)


def build_event_queue(redis_url: Optional[str] = None, stream_name: str = "class:transcript:chunks", priority: bool = False):
    redis_url = redis_url if redis_url is not None else os.getenv("ERP_REDIS_URL")
    if redis_url:
        try:
            return RedisStreamEventQueue(redis_url, stream_name)
        except ImportError:
            pass
    if priority or os.getenv("ERP_PRIORITY_QUEUE"):
        return PriorityEventQueue()
    return InMemoryEventQueue()

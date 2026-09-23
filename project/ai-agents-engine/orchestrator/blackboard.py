"""
Blackboard compartido entre agentes.

Mismo patrón de honestidad que el resto del proyecto (ver llm_client.py):
  - Por defecto usa un dict en memoria del proceso (funciona sin nada instalado).
  - Si existe ERP_REDIS_URL, usa Redis real (import diferido, no exige la
    dependencia si no se usa) para que el estado sobreviva reinicios del
    proceso y sea compartido entre workers reales en producción.

El "blackboard" es el estado compartido por sesión de clase (session_id):
cada agente lee lo que otros agentes ya escribieron ahí (tema detectado,
historial de decisiones, contadores de analítica) sin acoplarse
directamente entre sí — el patrón que ya usaba pizarra-backend/blackboard.js
en Node, portado aquí a Python para el motor real del ERP.
"""
import json
import os
import threading
from typing import Any, Optional


class InMemoryBlackboard:
    """Backend en memoria. Un dict anidado protegido por un lock simple,
    suficiente para un solo proceso (que es exactamente lo que este
    sandbox puede probar de verdad)."""

    def __init__(self):
        self._store: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._store.get(session_id, {}).get(key, default)

    def set(self, session_id: str, key: str, value: Any) -> None:
        with self._lock:
            self._store.setdefault(session_id, {})[key] = value

    def increment(self, session_id: str, key: str, by: int = 1) -> int:
        with self._lock:
            bucket = self._store.setdefault(session_id, {})
            bucket[key] = int(bucket.get(key, 0)) + by
            return bucket[key]

    def append(self, session_id: str, key: str, value: Any, max_len: int = 50) -> None:
        with self._lock:
            bucket = self._store.setdefault(session_id, {})
            history = bucket.setdefault(key, [])
            history.append(value)
            if len(history) > max_len:
                del history[: len(history) - max_len]

    def snapshot(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._store.get(session_id, {})))


class RedisBlackboard:
    """Backend real con Redis, usado solo si ERP_REDIS_URL está configurado.
    No se ejerce en este sandbox (no hay servidor Redis corriendo aquí);
    el punto de integración queda documentado igual que en llm_client.py."""

    def __init__(self, redis_url: str):
        import redis  # import local: no exige la dependencia en modo memoria

        self._r = redis.from_url(redis_url, decode_responses=True)
        self._prefix = "agents:blackboard:"

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    def get(self, session_id: str, key: str, default: Any = None) -> Any:
        raw = self._r.hget(self._key(session_id), key)
        return json.loads(raw) if raw is not None else default

    def set(self, session_id: str, key: str, value: Any) -> None:
        self._r.hset(self._key(session_id), key, json.dumps(value))

    def increment(self, session_id: str, key: str, by: int = 1) -> int:
        current = self.get(session_id, key, 0)
        new_value = int(current) + by
        self.set(session_id, key, new_value)
        return new_value

    def append(self, session_id: str, key: str, value: Any, max_len: int = 50) -> None:
        history = self.get(session_id, key, [])
        history.append(value)
        if len(history) > max_len:
            history = history[len(history) - max_len :]
        self.set(session_id, key, history)

    def snapshot(self, session_id: str) -> dict[str, Any]:
        raw = self._r.hgetall(self._key(session_id))
        return {k: json.loads(v) for k, v in raw.items()}


def build_blackboard(redis_url: Optional[str] = None):
    """Factory: elige backend según configuración, igual patrón que
    blackboard.js (detecta REDIS_URL / AMQP_URL automáticamente)."""
    redis_url = redis_url if redis_url is not None else os.getenv("ERP_REDIS_URL")
    if redis_url:
        try:
            return RedisBlackboard(redis_url)
        except ImportError:
            pass  # sin el paquete redis instalado, cae a memoria
    return InMemoryBlackboard()

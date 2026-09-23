"""
Tests del backend Redis del circuit breaker y del dead-letter queue —
NUEVOS. A diferencia de RedisBlackboard/RedisStreamEventQueue (que el
README marca honestamente como "no ejercitado en este sandbox"), estos
SÍ corren contra un Redis real levantado en este entorno
(`redis-server --daemonize yes`), porque el punto central a probar es
justo que el estado se COMPARTE entre procesos — algo que no se puede
verificar de verdad con un mock.

Si no hay Redis disponible (otro entorno, otra máquina), estos tests se
saltan explícitamente con un motivo claro — nunca se marcan como
"pasando" sin haber corrido, mismo estándar de honestidad del resto del
proyecto.

Correr con: pytest -v tests/test_resilience_redis.py
"""
import os
import sys
import time
import uuid

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from orchestrator.blackboard import InMemoryBlackboard
from orchestrator.dead_letter import DeadLetterQueue, build_dead_letter_queue
from orchestrator.loop_engine import AgentLoop
from orchestrator.queue_adapter import InMemoryEventQueue
from orchestrator.registry import (
    AgentRegistry,
    BaseAgent,
    CircuitState,
    RedisCircuitBreaker,
    build_circuit_breaker,
)

REDIS_URL = os.getenv("ERP_TEST_REDIS_URL", "redis://localhost:6379/3")
SESSION = "session-redis-test"


def _redis_available() -> bool:
    try:
        import redis

        client = redis.from_url(REDIS_URL, socket_connect_timeout=0.5)
        return client.ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(),
    reason=f"Redis no disponible en {REDIS_URL} en este entorno — se salta explícitamente, no se marca como probado.",
)


@pytest.fixture(autouse=True)
def _clean_redis_db():
    """Cada test corre contra claves únicas o limpia antes/después, para
    que el estado de un test no contamine al siguiente (Redis persiste
    entre tests dentro del mismo proceso pytest)."""
    import redis

    client = redis.from_url(REDIS_URL, decode_responses=True)
    client.flushdb()
    yield
    client.flushdb()


class FlakyAgent(BaseAgent):
    name = "flaky_agent_redis"
    interests = ("transcript_chunk",)

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0

    def handle(self, event, blackboard):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"fallo simulado #{self.calls}")
        return {"ok": True}


# --- El punto central: dos instancias == dos réplicas del mismo worker ------

def test_circuit_breaker_state_is_shared_across_independent_instances():
    """Simula 2 réplicas de ai-agents-engine: dos objetos RedisCircuitBreaker
    INDEPENDIENTES (sin referencia de memoria compartida entre sí) que
    apuntan al mismo Redis. Si la réplica A abre el circuito, la réplica B
    debe verlo abierto inmediatamente — esto es exactamente lo que el
    CircuitBreaker en memoria NO podía garantizar."""
    replica_a = build_circuit_breaker("shared_agent", redis_url=REDIS_URL, failure_threshold=2, cooldown_seconds=60)
    replica_b = build_circuit_breaker("shared_agent", redis_url=REDIS_URL, failure_threshold=2, cooldown_seconds=60)

    assert isinstance(replica_a, RedisCircuitBreaker)
    assert replica_a.state == CircuitState.CLOSED
    assert replica_b.state == CircuitState.CLOSED

    # La réplica A ve 2 fallos consecutivos y abre el circuito.
    replica_a.record_failure()
    replica_a.record_failure()
    assert replica_a.state == CircuitState.OPEN

    # La réplica B nunca vio un fallo directamente, pero comparte el
    # mismo Redis — debe ver el circuito abierto también.
    assert replica_b.state == CircuitState.OPEN
    assert replica_b.allow_request() is False


def test_circuit_breaker_half_open_recovery_via_redis():
    """Cooldown vencido -> half-open -> un intento de prueba exitoso
    (desde CUALQUIER réplica) cierra el circuito para todas."""
    clock = {"now": 1000.0}
    make = lambda: build_circuit_breaker(
        "recovering_agent", redis_url=REDIS_URL, failure_threshold=1, cooldown_seconds=10,
        clock=lambda: clock["now"],
    )
    replica_a = make()
    replica_b = make()

    replica_a.record_failure()
    assert replica_a.state == CircuitState.OPEN
    assert replica_b.allow_request() is False  # todavía en cooldown

    clock["now"] += 11  # pasa el cooldown
    assert replica_b.allow_request() is True  # transiciona a half-open
    assert replica_a.state == CircuitState.HALF_OPEN  # visible desde la otra réplica

    replica_b.record_success()
    assert replica_a.state == CircuitState.CLOSED
    assert replica_a.consecutive_failures == 0


@pytest.mark.asyncio
async def test_agent_loop_with_redis_backed_registry_shares_state_between_loops():
    """Integración de punta a punta: dos AgentLoop distintos (simulando 2
    procesos/réplicas), cada uno con su propio AgentRegistry, pero ambos
    construidos con circuit breakers apuntando al mismo Redis. El agente
    roto se abre en el loop 1 y el loop 2 lo respeta sin haber visto sus
    fallos directamente."""
    factory = lambda name: build_circuit_breaker(name, redis_url=REDIS_URL, failure_threshold=1, cooldown_seconds=999)

    agent_replica_1 = FlakyAgent(fail_times=999)
    registry_1 = AgentRegistry(circuit_breaker_factory=factory)
    registry_1.register(agent_replica_1)
    loop_1 = AgentLoop(event_queue=InMemoryEventQueue(), blackboard=InMemoryBlackboard(), registry=registry_1)

    agent_replica_2 = FlakyAgent(fail_times=999)
    registry_2 = AgentRegistry(circuit_breaker_factory=factory)
    registry_2.register(agent_replica_2)
    loop_2 = AgentLoop(event_queue=InMemoryEventQueue(), blackboard=InMemoryBlackboard(), registry=registry_2)

    await loop_1.event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "clase"})
    await loop_1.run_n(1)  # el agente falla 1 vez -> circuito se abre en Redis

    await loop_2.event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "clase"})
    (result_2,) = await loop_2.run_n(1)

    # loop_2 nunca ejecutó su propia copia del agente para este evento:
    # el circuito ya estaba abierto en Redis desde loop_1.
    assert agent_replica_2.calls == 0
    flaky_result = [r for r in result_2.agent_results if r.agent_name == "flaky_agent_redis"][0]
    assert flaky_result.circuit_skipped is True


# --- Dead-letter queue compartido -------------------------------------------

def test_dead_letter_queue_is_shared_across_replicas():
    """Un evento que falla en la réplica A debe ser visible y reintentable
    desde la réplica B (ej. un panel de soporte corriendo en otro pod)."""
    dlq_a = build_dead_letter_queue(redis_url=REDIS_URL, key=f"test:dlq:{uuid.uuid4()}")
    dlq_b = build_dead_letter_queue(redis_url=REDIS_URL, key=dlq_a._key)

    dlq_a.push({"session_id": SESSION, "raw_text": "texto problemático"}, reason="JSON inválido del LLM")

    assert len(dlq_b) == 1
    entries = dlq_b.all_entries()
    assert entries[0].reason == "JSON inválido del LLM"
    assert entries[0].event["raw_text"] == "texto problemático"

    # pop_for_retry() desde la réplica B vacía la cola para AMBAS.
    events = dlq_b.pop_for_retry()
    assert len(events) == 1
    assert len(dlq_a) == 0


def test_build_dead_letter_queue_falls_back_to_memory_without_redis_url():
    """Sin ERP_REDIS_URL ni redis_url explícito, sigue siendo memoria de
    proceso — no rompe el comportamiento por defecto del resto del
    proyecto para quien no tiene Redis configurado."""
    os.environ.pop("ERP_REDIS_URL", None)
    dlq = build_dead_letter_queue(redis_url=None)
    assert isinstance(dlq, DeadLetterQueue)

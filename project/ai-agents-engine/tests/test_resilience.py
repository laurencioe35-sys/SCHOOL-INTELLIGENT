"""
Tests de la capa de resiliencia — NUEVA en este proyecto (no existía
antes de esta iteración): circuit breaker por agente, cola con
prioridad, y aislamiento del pipeline base vía dead-letter queue.

Mismo estándar de honestidad que el resto del proyecto: todo corre de
verdad en este sandbox, sin sleeps reales (reloj inyectado) y sin Redis
ni API key.

Correr con: pytest -v tests/test_resilience.py
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from orchestrator.blackboard import InMemoryBlackboard
from orchestrator.dead_letter import DeadLetterQueue
from orchestrator.loop_engine import AgentLoop
from orchestrator.queue_adapter import InMemoryEventQueue, PriorityEventQueue
from orchestrator.registry import AgentRegistry, BaseAgent, CircuitBreaker, CircuitState

SESSION = "session-resilience-001"


class FlakyAgent(BaseAgent):
    """Falla las primeras N veces que se le llama, luego funciona bien
    — simula un agente que depende de un proveedor LLM con una caída
    temporal y se recupera solo."""

    name = "flaky_agent"
    interests = ("transcript_chunk",)

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0

    def handle(self, event, blackboard):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"fallo simulado #{self.calls}")
        return {"ok": True, "call_number": self.calls}


class FakeClock:
    """Reloj controlado a mano para probar cooldown del circuit breaker
    sin depender de tiempo real ni sleeps."""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _build_loop(extra_agents=None, breaker_factory=None, event_queue=None, dlq=None):
    event_queue = event_queue or InMemoryEventQueue()
    blackboard = InMemoryBlackboard()
    registry = AgentRegistry(circuit_breaker_factory=breaker_factory)
    for agent in (extra_agents or []):
        registry.register(agent)
    dlq = dlq if dlq is not None else DeadLetterQueue()
    loop = AgentLoop(event_queue=event_queue, blackboard=blackboard, registry=registry, dead_letter_queue=dlq)
    return loop, event_queue, blackboard, registry, dlq


# --- Circuit breaker ------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_opens_after_consecutive_failures_and_skips_agent():
    """Después de N fallos seguidos, el agente se salta (no se vuelve a
    invocar) — se ahorra latencia/costo de LLM en un agente que ya
    sabemos que está fallando."""
    clock = FakeClock()
    always_broken = FlakyAgent(fail_times=999)  # nunca se recupera en esta prueba
    loop, event_queue, blackboard, registry, _ = _build_loop(
        extra_agents=[always_broken],
        breaker_factory=lambda name: CircuitBreaker(failure_threshold=2, cooldown_seconds=60, clock=clock),
    )

    for _ in range(4):
        await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "clase de prueba"})

    results = await loop.run_n(4)

    # Los primeros 2 ciclos SÍ invocan al agente (y fallan); a partir del
    # 3ro el circuito ya está abierto y se salta sin ejecutar handle().
    assert always_broken.calls == 2
    breaker = registry.breaker_for("flaky_agent")
    assert breaker.state == CircuitState.OPEN

    skipped = [r for cycle in results for r in cycle.agent_results if r.agent_name == "flaky_agent" and r.circuit_skipped]
    assert len(skipped) == 2  # los 2 últimos ciclos se saltaron el agente


@pytest.mark.asyncio
async def test_circuit_recovers_via_half_open_after_cooldown():
    """Pasado el cooldown, el breaker entra en half-open, permite UN
    intento de prueba, y si el agente ya se recuperó, vuelve a closed
    automáticamente — sin reiniciar ningún proceso a mano."""
    clock = FakeClock()
    recovering_agent = FlakyAgent(fail_times=2)  # falla 2 veces, la 3ra funciona
    loop, event_queue, blackboard, registry, _ = _build_loop(
        extra_agents=[recovering_agent],
        breaker_factory=lambda name: CircuitBreaker(failure_threshold=2, cooldown_seconds=30, clock=clock),
    )

    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "a"})
    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "b"})
    await loop.run_n(2)

    breaker = registry.breaker_for("flaky_agent")
    assert breaker.state == CircuitState.OPEN
    assert recovering_agent.calls == 2

    # Todavía dentro del cooldown: se sigue saltando, no gasta una llamada más.
    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "c"})
    (result_during_cooldown,) = await loop.run_n(1)
    assert recovering_agent.calls == 2
    assert result_during_cooldown.agent_results[0].circuit_skipped

    # Pasa el cooldown -> half-open -> se permite un intento de prueba,
    # el agente ya se recuperó (fail_times=2), así que el circuito cierra.
    clock.advance(31)
    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "d"})
    (result_after_cooldown,) = await loop.run_n(1)

    assert recovering_agent.calls == 3
    assert result_after_cooldown.agent_results[0].ok is True
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_other_agents_unaffected_by_one_agents_open_circuit():
    """El circuito de un agente es independiente del de otro — un agente
    sano sigue corriendo con normalidad aunque otro esté offline."""
    healthy_calls = {"count": 0}

    class HealthyAgent(BaseAgent):
        name = "healthy_agent"
        interests = ("transcript_chunk",)

        def handle(self, event, blackboard):
            healthy_calls["count"] += 1
            return {"ok": True}

    clock = FakeClock()
    broken = FlakyAgent(fail_times=999)
    loop, event_queue, _, registry, _ = _build_loop(
        extra_agents=[broken, HealthyAgent()],
        breaker_factory=lambda name: CircuitBreaker(failure_threshold=1, cooldown_seconds=60, clock=clock),
    )

    for _ in range(3):
        await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "x"})
    await loop.run_n(3)

    assert registry.breaker_for("flaky_agent").state == CircuitState.OPEN
    assert registry.breaker_for("healthy_agent").state == CircuitState.CLOSED
    assert healthy_calls["count"] == 3  # nunca se saltó
    assert "flaky_agent" in registry.open_circuits()
    assert "healthy_agent" not in registry.open_circuits()


# --- Cola con prioridad -----------------------------------------------------

@pytest.mark.asyncio
async def test_priority_queue_serves_urgent_events_before_earlier_normal_ones():
    """Tres eventos 'normal' publicados primero, y un 'urgent' publicado
    después, deben salir con el urgente primero — justo lo que
    InMemoryEventQueue (FIFO) NO puede garantizar."""
    queue = PriorityEventQueue()

    await queue.publish({"session_id": SESSION, "raw_text": "normal-1", "priority": "normal"})
    await queue.publish({"session_id": SESSION, "raw_text": "normal-2", "priority": "normal"})
    await queue.publish({"session_id": SESSION, "raw_text": "normal-3", "priority": "normal"})
    await queue.publish({"session_id": SESSION, "raw_text": "urgent-1", "priority": "urgent"})

    first = await queue.consume()
    assert first["raw_text"] == "urgent-1"

    # Dentro de la misma prioridad, se respeta el orden de llegada (FIFO).
    second = await queue.consume()
    third = await queue.consume()
    fourth = await queue.consume()
    assert [second["raw_text"], third["raw_text"], fourth["raw_text"]] == ["normal-1", "normal-2", "normal-3"]


@pytest.mark.asyncio
async def test_priority_queue_defaults_to_normal_when_unspecified():
    queue = PriorityEventQueue()
    await queue.publish({"session_id": SESSION, "raw_text": "sin-prioridad"})
    await queue.publish({"session_id": SESSION, "raw_text": "baja", "priority": "low"})

    first = await queue.consume()
    assert first["raw_text"] == "sin-prioridad"  # normal > low en urgencia


# --- Dead-letter queue del pipeline base ------------------------------------

@pytest.mark.asyncio
async def test_core_pipeline_failure_goes_to_dead_letter_and_loop_survives():
    """Antes de este cambio, una excepción en el pipeline base (context ->
    pedagogical -> ui_compiler) tumbaba run_forever() por completo. Ahora
    el evento problemático va al dead-letter y el loop sigue vivo para
    procesar el resto de la clase con normalidad."""
    dlq = DeadLetterQueue()
    loop, event_queue, blackboard, _, _ = _build_loop(dlq=dlq)

    # Monkeypatch puntual: forzamos que el pipeline base falle para ESTE
    # evento, simulando un LLM real devolviendo un JSON inválido.
    import orchestrator.loop_engine as loop_engine_module

    original_extract = loop_engine_module.extract_semantic_chunk

    def _boom(raw_text):
        if raw_text == "texto-que-rompe-el-pipeline":
            raise ValueError("JSON del LLM no cumple SemanticChunk")
        return original_extract(raw_text)

    loop_engine_module.extract_semantic_chunk = _boom
    try:
        await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "texto-que-rompe-el-pipeline"})
        await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "Hoy vamos a estudiar el triangulo equilatero"})

        results = await loop.run_n(2)  # si el loop se cayera, esto ni siquiera terminaría de correr
    finally:
        loop_engine_module.extract_semantic_chunk = original_extract

    assert results[0].core_pipeline is None
    assert results[0].core_pipeline_error is not None
    assert results[1].core_pipeline is not None  # el SIGUIENTE evento se procesó normal

    assert len(dlq) == 1
    entry = dlq.all_entries()[0]
    assert entry.event["raw_text"] == "texto-que-rompe-el-pipeline"
    assert blackboard.get(SESSION, "core_pipeline_dead_letters") == 1

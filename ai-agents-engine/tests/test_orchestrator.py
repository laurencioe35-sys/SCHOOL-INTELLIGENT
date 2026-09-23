"""
Tests del motor de loop + registro de agentes ("otro nivel" del
ai-agents-engine). Todos corren con la cola y el blackboard en memoria
(sin Redis, sin API key) — igual honestidad que el resto del proyecto:
lo que dice "probado" aquí, corrió de verdad en este entorno.

Correr con: pytest -v (dentro de ai-agents-engine/)
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from agents_v2.analytics_agent import AnalyticsAgent
from agents_v2.content_generator_agent import ContentGeneratorAgent
from agents_v2.grading_agent import GradingAgent
from agents_v2.teacher_response_agent import TeacherResponseAgent
from config.schemas import AnalyticsSnapshot, GeneratedQuiz, GradingResult
from orchestrator.blackboard import InMemoryBlackboard
from orchestrator.loop_engine import AgentLoop
from orchestrator.queue_adapter import InMemoryEventQueue
from orchestrator.registry import AgentRegistry, BaseAgent

SESSION = "session-test-001"


class BrokenAgent(BaseAgent):
    """Agente que siempre falla, para probar aislamiento de errores."""
    name = "broken_agent"
    interests = ("transcript_chunk",)

    def handle(self, event, blackboard):
        raise RuntimeError("fallo intencional para probar aislamiento")


def _build_loop(extra_agents=None, output_queue=None):
    event_queue = InMemoryEventQueue()
    blackboard = InMemoryBlackboard()
    registry = AgentRegistry()
    for agent in (extra_agents or []):
        registry.register(agent)
    loop = AgentLoop(event_queue=event_queue, blackboard=blackboard, registry=registry, output_queue=output_queue)
    return loop, event_queue, blackboard, registry


@pytest.mark.asyncio
async def test_loop_processes_multiple_chunks_continuously():
    """El loop real consume varios eventos, uno tras otro, sin que nadie
    vuelva a invocar nada a mano por evento (a diferencia de
    process_chunk() en main_agents.py)."""
    loop, event_queue, blackboard, _ = _build_loop()

    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "Hoy vamos a estudiar el triangulo equilatero"})
    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "La formula del area es base por altura sobre dos"})
    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "Bien, pasemos al siguiente tema"})

    results = await loop.run_n(3)

    assert len(results) == 3
    assert results[0].core_pipeline["semantic_chunk"]["topic"] == "geometria"
    assert results[0].core_pipeline["decision"]["action"] == "render_3d_object"
    assert results[2].core_pipeline["decision"]["action"] == "no_action"
    # El blackboard retiene lo último que dejó el pipeline para que otros
    # agentes lo lean en el mismo ciclo.
    assert blackboard.get(SESSION, "last_topic") == "general"
    assert loop.processed_events == 3
    assert loop.failed_events == 0


@pytest.mark.asyncio
async def test_agent_failure_is_isolated_and_counted():
    """Un agente roto no debe tumbar el loop ni impedir que otros agentes
    del mismo ciclo (o eventos siguientes) se ejecuten con normalidad."""
    loop, event_queue, blackboard, _ = _build_loop(extra_agents=[BrokenAgent(), AnalyticsAgent()])

    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "Hoy vamos a estudiar el triangulo equilatero"})
    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "Otro fragmento cualquiera"})

    results = await loop.run_n(2)

    broken_results = [r for cycle in results for r in cycle.agent_results if r.agent_name == "broken_agent"]
    analytics_results = [r for cycle in results for r in cycle.agent_results if r.agent_name == "analytics_agent"]

    assert all(not r.ok for r in broken_results)
    assert all(r.ok for r in analytics_results)  # el otro agente no se vio afectado
    assert blackboard.get(SESSION, "agent_errors") == 2  # uno por cada evento


@pytest.mark.asyncio
async def test_grading_agent_via_loop_produces_valid_schema():
    """El registro de agentes ('receptor de multiagentes'): un agente
    nuevo, registrado sin tocar loop_engine.py, procesa un evento de tipo
    distinto (student_submission) y su salida cumple el contrato Pydantic."""
    loop, event_queue, blackboard, _ = _build_loop(extra_agents=[GradingAgent()])

    await event_queue.publish({
        "type": "student_submission", "session_id": SESSION,
        "question": "¿Qué caracteriza a un triángulo equilátero?",
        "student_answer": "Que sus tres lados y sus tres angulos son iguales",
        "key_points": ["tres lados iguales", "tres angulos iguales"],
    })
    results = await loop.run_n(1)

    grading_result = results[0].agent_results[0]
    assert grading_result.ok
    assert isinstance(grading_result.data, GradingResult)
    assert grading_result.data.score == 1.0
    assert grading_result.data.needs_teacher_review is False
    assert blackboard.get(SESSION, "submissions_graded") == 1


@pytest.mark.asyncio
async def test_grading_agent_flags_weak_answer_for_review():
    loop, event_queue, _, _ = _build_loop(extra_agents=[GradingAgent()])
    await event_queue.publish({
        "type": "student_submission", "session_id": SESSION,
        "question": "¿Qué caracteriza a un triángulo equilátero?",
        "student_answer": "no se",
        "key_points": ["tres lados iguales", "tres angulos iguales"],
    })
    results = await loop.run_n(1)
    grading_result = results[0].agent_results[0].data
    assert grading_result.needs_teacher_review is True
    assert grading_result.score < 0.5


@pytest.mark.asyncio
async def test_content_generator_uses_blackboard_topic_from_core_pipeline():
    """El content_generator_agent no vuelve a detectar el tema: lo lee del
    blackboard, escrito por el loop en el mismo ciclo — prueba directa del
    patrón Blackboard funcionando entre dos agentes independientes."""
    loop, event_queue, blackboard, _ = _build_loop(extra_agents=[ContentGeneratorAgent()])

    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "Hoy vamos a estudiar el triangulo equilatero"})
    results = await loop.run_n(1)

    quiz_result = results[0].agent_results[0]
    assert quiz_result.ok
    assert isinstance(quiz_result.data, GeneratedQuiz)
    assert quiz_result.data.topic == "geometria"
    assert len(quiz_result.data.questions) >= 1


@pytest.mark.asyncio
async def test_content_generator_skips_low_confidence_or_general_topic():
    """Regla de negocio: no generar quiz de fragmentos de transición
    ('general' o baja confianza) — se prueba explícitamente el caso
    negativo, no solo el camino feliz."""
    loop, event_queue, _, _ = _build_loop(extra_agents=[ContentGeneratorAgent()])

    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "Bien, pasemos al siguiente tema"})
    results = await loop.run_n(1)

    quiz_result = results[0].agent_results[0]
    assert quiz_result.ok
    assert quiz_result.data is None


@pytest.mark.asyncio
async def test_analytics_agent_aggregates_across_multiple_agents_and_events():
    """Test de integración de los 3 agentes nuevos juntos + el pipeline
    base, corriendo en el loop real por varios ciclos — el escenario más
    parecido a producción que se puede probar en este sandbox."""
    loop, event_queue, blackboard, _ = _build_loop(
        extra_agents=[GradingAgent(), ContentGeneratorAgent(), AnalyticsAgent()]
    )

    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "Hoy vamos a estudiar el triangulo equilatero"})
    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "La formula del area es base por altura sobre dos"})
    await event_queue.publish({
        "type": "student_submission", "session_id": SESSION,
        "question": "¿Qué caracteriza a un triángulo equilátero?",
        "student_answer": "Que sus tres lados y sus tres angulos son iguales",
        "key_points": ["tres lados iguales", "tres angulos iguales"],
    })

    await loop.run_n(3)
    snapshot = AnalyticsAgent.snapshot(SESSION, blackboard)

    assert isinstance(snapshot, AnalyticsSnapshot)
    assert snapshot.chunks_processed == 2
    assert "geometria" in snapshot.topics_covered
    assert snapshot.action_counts.get("render_3d_object") == 1
    assert snapshot.submissions_graded == 1
    assert snapshot.agent_errors == 0


@pytest.mark.asyncio
async def test_output_queue_receives_aggregated_result_per_cycle():
    """El loop publica un resultado agregado por ciclo en una cola de
    salida desacoplada — el punto donde multimedia-stream-server se
    conectaría en producción para relayar al frontend por WebSocket."""
    output_queue = InMemoryEventQueue()
    loop, event_queue, _, _ = _build_loop(extra_agents=[AnalyticsAgent()], output_queue=output_queue)

    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "Hoy vamos a estudiar el triangulo equilatero"})
    await loop.run_n(1)

    assert output_queue.qsize() == 1
    published = await output_queue.consume()
    assert published["session_id"] == SESSION
    assert published["core_pipeline"]["decision"]["action"] == "render_3d_object"
    assert any(r["agent_name"] == "analytics_agent" and r["ok"] for r in published["agent_results"])
    analytics = next(r for r in published["agent_results"] if r["agent_name"] == "analytics_agent")
    assert analytics["data"]["chunks_processed"] == 1


@pytest.mark.asyncio
async def test_loop_publishes_teacher_response_for_transcript():
    output_queue = InMemoryEventQueue()
    loop, event_queue, _, _ = _build_loop(extra_agents=[TeacherResponseAgent()], output_queue=output_queue)

    await event_queue.publish({
        "type": "transcript_chunk", "session_id": SESSION,
        "raw_text": "Explica el binomio al cuadrado",
    })
    await loop.run_n(1)
    published = await output_queue.consume()

    response = next(item for item in published["agent_results"] if item["agent_name"] == "teacher_response_agent")
    assert response["ok"] is True
    assert response["data"]["message"]
    assert response["data"]["session_id"] == SESSION


@pytest.mark.asyncio
async def test_loop_uses_teacher_generated_board_component_not_raw_prompt(monkeypatch):
    monkeypatch.setattr(
        "agents_v2.teacher_response_agent.call_llm",
        lambda *_args, **_kwargs: '''{
            "message": "Ejemplo listo para que el docente lo revise.",
            "destination": "board",
            "component": {"component_type": "formula", "payload": {"text": "(x+2)^2=x^2+4x+4"}}
        }''',
    )
    output_queue = InMemoryEventQueue()
    loop, event_queue, _, _ = _build_loop(extra_agents=[TeacherResponseAgent()], output_queue=output_queue)
    await event_queue.publish({"type": "transcript_chunk", "session_id": SESSION, "raw_text": "Ejemplo de binomios"})

    await loop.run_n(1)
    published = await output_queue.consume()

    assert published["core_pipeline"]["source"] == "teacher_response_agent"
    assert published["core_pipeline"]["ui_component"]["payload"]["text"] == "(x+2)^2=x^2+4x+4"


@pytest.mark.asyncio
async def test_loop_returns_manual_transcription_without_running_agents():
    output_queue = InMemoryEventQueue()
    loop, event_queue, _, _ = _build_loop(output_queue=output_queue)
    await event_queue.publish({
        "type": "transcription_ready", "session_id": SESSION,
        "tenant_id": "tenant-1", "text": "Explica binomio al cuadrado",
    })

    await loop.run_n(1)
    published = await output_queue.consume()

    assert published["transcription"] == {"text": "Explica binomio al cuadrado", "dispatch_mode": "manual"}
    assert published["agent_results"] == []

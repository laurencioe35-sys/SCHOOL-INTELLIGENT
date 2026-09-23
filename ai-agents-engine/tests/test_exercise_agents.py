"""
Tests de los agentes de materia (subject_agents / ExerciseAgent).
Corren con el LLM mock (sin API key) — igual honestidad que el resto:
lo que dice "probado" corrió de verdad, y ningún enunciado generado aquí
proviene de ningún libro con copyright (son ejemplos originales del mock,
ver config/llm_client.py::_mock_exercise_response).
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from agents_v2.exercise_agent import SUBJECT_CATALOG, ExerciseAgent, build_all_subject_agents
from config.schemas import SolvedExercise
from orchestrator.blackboard import InMemoryBlackboard
from orchestrator.loop_engine import AgentLoop
from orchestrator.queue_adapter import InMemoryEventQueue
from orchestrator.registry import AgentRegistry

SESSION = "session-exercises-001"


def _build_loop_with_all_subjects():
    event_queue = InMemoryEventQueue()
    blackboard = InMemoryBlackboard()
    registry = AgentRegistry()
    for agent in build_all_subject_agents():
        registry.register(agent)
    loop = AgentLoop(event_queue=event_queue, blackboard=blackboard, registry=registry)
    return loop, event_queue, blackboard, registry


@pytest.mark.parametrize("subject", list(SUBJECT_CATALOG.keys()))
@pytest.mark.asyncio
async def test_every_subject_produces_a_valid_solved_exercise(subject):
    """Cubre TODAS las materias pedidas (matemática por áreas, física,
    química, biología, anatomía, inglés): cada una debe producir un
    SolvedExercise válido, con al menos 2 pasos de razonamiento."""
    loop, event_queue, _, _ = _build_loop_with_all_subjects()
    topic = SUBJECT_CATALOG[subject][0]

    await event_queue.publish({
        "type": "exercise_request", "session_id": SESSION,
        "subject": subject, "topic": topic, "difficulty": "basico",
    })
    results = await loop.run_n(1)

    matching = [r for r in results[0].agent_results if r.ok and r.data is not None]
    assert len(matching) == 1, f"se esperaba exactamente 1 agente respondiendo para {subject}"

    exercise = matching[0].data
    assert isinstance(exercise, SolvedExercise)
    assert exercise.subject == subject
    assert len(exercise.steps) >= 2
    assert exercise.statement.strip() != ""
    assert exercise.final_answer.strip() != ""


@pytest.mark.asyncio
async def test_only_the_matching_subject_agent_responds():
    """Aislamiento por materia: pedir un ejercicio de Física no debe
    generar respuestas de los agentes de las otras 9 materias."""
    loop, event_queue, _, _ = _build_loop_with_all_subjects()

    await event_queue.publish({
        "type": "exercise_request", "session_id": SESSION,
        "subject": "Física", "topic": "cinemática (MRU/MRUV)", "difficulty": "basico",
    })
    results = await loop.run_n(1)

    non_none = [r for r in results[0].agent_results if r.data is not None]
    assert len(non_none) == 1
    assert non_none[0].agent_name == "exercise_agent__física"


@pytest.mark.asyncio
async def test_math_algebra_exercise_is_actually_solved_correctly():
    """No basta con que el esquema sea válido: el ejercicio mock de
    álgebra debe estar realmente bien resuelto (3x + 7 = 22 -> x = 5),
    para no generar contenido educativo incorrecto ni con el mock."""
    loop, event_queue, _, _ = _build_loop_with_all_subjects()
    await event_queue.publish({
        "type": "exercise_request", "session_id": SESSION,
        "subject": "Matemática - Álgebra", "topic": "ecuaciones lineales", "difficulty": "basico",
    })
    results = await loop.run_n(1)
    exercise = [r.data for r in results[0].agent_results if r.data is not None][0]
    assert "x = 5" in exercise.final_answer


@pytest.mark.asyncio
async def test_exercise_generation_updates_blackboard_counters():
    loop, event_queue, blackboard, _ = _build_loop_with_all_subjects()
    await event_queue.publish({
        "type": "exercise_request", "session_id": SESSION,
        "subject": "Química", "topic": "masa molar y moles", "difficulty": "intermedio",
    })
    await loop.run_n(1)
    assert blackboard.get(SESSION, "exercises_generated:química") == 1
    history = blackboard.get(SESSION, "exercises_history", [])
    assert len(history) == 1
    assert history[0]["subject"] == "Química"


def test_subject_catalog_covers_all_requested_areas():
    """Prueba explícita de cobertura del pedido: todas las áreas de
    matemática mencionadas, más física, química, biología, anatomía e
    inglés, están en el catálogo."""
    required_keywords = [
        "álgebra", "geometría", "trigonometría", "cálculo", "estadística",
        "física", "química", "biología", "anatomía", "inglés",
    ]
    catalog_text = " | ".join(SUBJECT_CATALOG.keys()).lower()
    for kw in required_keywords:
        assert kw in catalog_text, f"falta cobertura de '{kw}' en SUBJECT_CATALOG"

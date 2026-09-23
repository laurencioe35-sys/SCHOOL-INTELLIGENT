"""
Runner del harness de evals: por cada EvalCase, invoca el agente REAL
correspondiente (no una simulación del harness) con el input del caso, y
corre sus checks de calidad sobre la salida.

Separado de golden_dataset.py y checks.py a propósito (single
responsibility): el dataset declara QUÉ probar, checks.py declara CÓMO
evaluar una salida, este módulo declara CÓMO invocar cada agente — así
agregar un agente nuevo al eval es: (1) una entrada en AGENT_INVOKERS,
(2) casos en golden_dataset.py, sin tocar la lógica de ejecución.
"""
import time
from typing import Any

from evals.eval_types import CaseResult, EvalCase

from agents.context_agent import extract_semantic_chunk
from agents.pedagogical_agent import decide_pedagogical_action
from agents.ui_compiler_agent import compile_ui_component
from agents_v2.grading_agent import GradingAgent
from agents_v2.content_generator_agent import ContentGeneratorAgent, MIN_CONFIDENCE_TO_GENERATE
from agents_v2.exercise_agent import ExerciseAgent
from config.schemas import SemanticChunk, PedagogicalDecision
from orchestrator.blackboard import InMemoryBlackboard


def _invoke_context_agent(input: dict[str, Any]):
    return extract_semantic_chunk(input["raw_text"])


def _invoke_pedagogical_agent(input: dict[str, Any]):
    chunk = SemanticChunk(text=input["text"], topic="desconocido", confidence=0.9)
    return decide_pedagogical_action(chunk)


def _invoke_ui_compiler_agent(input: dict[str, Any]):
    decision = PedagogicalDecision(action="render_3d_object", reason="eval harness", priority="high")
    return compile_ui_component(input["chunk_text"], decision, input["session_id"])


def _invoke_grading_agent(input: dict[str, Any]):
    agent = GradingAgent()
    blackboard = InMemoryBlackboard()
    event = {
        "question": input["question"],
        "student_answer": input["student_answer"],
        "key_points": input["key_points"],
        "session_id": "eval-session",
    }
    return agent.handle(event, blackboard)


def _invoke_content_generator_agent(input: dict[str, Any]):
    agent = ContentGeneratorAgent()
    blackboard = InMemoryBlackboard()
    session_id = "eval-session"
    # El ContentGeneratorAgent lee topic/confidence del blackboard (los
    # deja ahí el context_agent en el loop real) — el harness los
    # precarga para no depender de correr el pipeline completo por cada caso.
    blackboard.set(session_id, "last_topic", "geometria")
    blackboard.set(session_id, "last_confidence", max(MIN_CONFIDENCE_TO_GENERATE, 0.8))
    event = {"raw_text": input["raw_text"], "session_id": session_id}
    return agent.handle(event, blackboard)


def _invoke_exercise_agent(input: dict[str, Any]):
    agent = ExerciseAgent(subject=input["subject"])
    blackboard = InMemoryBlackboard()
    event = {
        "subject": input["subject"],
        "topic": input["topic"],
        "difficulty": input["difficulty"],
        "session_id": "eval-session",
    }
    return agent.handle(event, blackboard)


AGENT_INVOKERS = {
    "context_agent": _invoke_context_agent,
    "pedagogical_agent": _invoke_pedagogical_agent,
    "ui_compiler_agent": _invoke_ui_compiler_agent,
    "grading_agent": _invoke_grading_agent,
    "content_generator_agent": _invoke_content_generator_agent,
    "exercise_agent": _invoke_exercise_agent,
}


def run_case(case: EvalCase) -> CaseResult:
    invoker = AGENT_INVOKERS.get(case.agent)
    if invoker is None:
        return CaseResult(case.id, case.agent, passed=False, score=0.0, check_results=[],
                           error=f"no hay invoker registrado para el agente {case.agent!r}")

    try:
        output = invoker(case.input)
    except Exception as exc:  # noqa: BLE001 — un caso que crashea es un fallo del eval, no del harness
        return CaseResult(case.id, case.agent, passed=False, score=0.0, check_results=[], error=str(exc))

    check_results = [check(output) for check in case.checks]
    if not check_results:
        return CaseResult(case.id, case.agent, passed=True, score=1.0, check_results=[])

    score = sum(1 for c in check_results if c.passed) / len(check_results)
    passed = all(c.passed for c in check_results)
    return CaseResult(case.id, case.agent, passed=passed, score=score, check_results=check_results)


def run_cases(cases: list[EvalCase]) -> list[CaseResult]:
    return [run_case(case) for case in cases]

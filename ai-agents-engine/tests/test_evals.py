"""
Tests del harness de evals.

Dos cosas distintas se prueban aquí:
  1. Que el dataset dorado actual pasa el gate de calidad (regresión: si
     alguien rompe un agente o el mock, este test falla en CI).
  2. Que el harness en sí DETECTA una regresión real cuando se inyecta
     una — sin esto, un harness que siempre dice "PASS" pasaría este
     mismo archivo de tests sin que sirva de nada.
"""
import pytest

from evals.golden_dataset import ALL_CASES, GRADING_AGENT_CASES
from evals.runner import run_cases, run_case
from evals.checks import check_grading_never_perfect_score_on_empty
from evals.eval_types import CaseResult


def test_golden_dataset_passes_quality_gate():
    results = run_cases(ALL_CASES)
    failed = [r for r in results if not r.passed]
    assert not failed, "Casos fallidos: " + ", ".join(
        f"{r.case_id} ({[c.name for c in r.check_results if not c.passed]})" for r in failed
    )
    overall_pass_rate = sum(1 for r in results if r.passed) / len(results)
    assert overall_pass_rate >= 0.85


def test_every_agent_type_has_at_least_one_case():
    """Si se agrega un agente nuevo sin agregar casos al eval, este test
    lo marca — evita que el harness quede desactualizado en silencio."""
    from evals.runner import AGENT_INVOKERS
    agents_with_cases = {case.agent for case in ALL_CASES}
    assert agents_with_cases == set(AGENT_INVOKERS.keys())


def test_harness_detects_a_real_regression():
    """Prueba que el check de seguridad de grading SÍ detecta una nota
    inflada — construye una salida corrupta a mano (simulando el bug que
    este check existe para atrapar) y confirma que el CheckResult marca
    passed=False, no un falso verde silencioso."""
    from config.schemas import GradingResult

    corrupted_output = GradingResult(
        student_answer="",
        score=0.95,  # nota alta inventada para una respuesta vacía: el bug real
        matched_key_points=[],
        feedback="calificación automática",
        needs_teacher_review=False,
    )
    result = check_grading_never_perfect_score_on_empty(corrupted_output)
    assert result.passed is False, "el check debe detectar la nota inflada, no dejarla pasar"


def test_run_case_reports_error_without_crashing_on_unknown_agent():
    from evals.eval_types import EvalCase
    bogus_case = EvalCase(id="bogus", agent="agente_que_no_existe", input={}, checks=[])
    result = run_case(bogus_case)
    assert isinstance(result, CaseResult)
    assert result.passed is False
    assert "no hay invoker registrado" in result.error

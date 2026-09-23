"""
Verificaciones de calidad, una función por criterio. Cada función recibe
la salida YA VALIDADA por Pydantic (el schema garantiza la forma; estas
funciones evalúan el CONTENIDO: ¿la decisión tiene sentido para esta
entrada específica?).

Separadas en funciones pequeñas y nombradas (no un solo scorer gigante)
para que el reporte de `run_evals.py` diga exactamente qué falló —
"check_grading_never_perfect_score_on_empty" es mucho más accionable que
"score bajo".
"""
from evals.eval_types import CheckResult


def check_topic_matches_geometry(output) -> CheckResult:
    passed = output.topic == "geometria"
    return CheckResult("topic_matches_geometry", passed, f"topic={output.topic!r}")


def check_topic_is_general_for_unrelated_text(output) -> CheckResult:
    passed = output.topic == "general"
    return CheckResult("topic_is_general_for_unrelated_text", passed, f"topic={output.topic!r}")


def check_confidence_in_range(output) -> CheckResult:
    passed = 0.0 <= output.confidence <= 1.0
    return CheckResult("confidence_in_range", passed, f"confidence={output.confidence}")


def check_action_render_3d_for_shape_mention(output) -> CheckResult:
    passed = output.action == "render_3d_object"
    return CheckResult("action_render_3d_for_shape_mention", passed, f"action={output.action!r}")


def check_action_render_formula_for_equation(output) -> CheckResult:
    passed = output.action == "render_formula"
    return CheckResult("action_render_formula_for_equation", passed, f"action={output.action!r}")


def check_action_no_action_for_greeting(output) -> CheckResult:
    passed = output.action == "no_action"
    return CheckResult("action_no_action_for_greeting", passed, f"action={output.action!r}")


def check_ui_component_type_matches_shape(output) -> CheckResult:
    passed = output is not None and output.component_type == "object3d"
    return CheckResult("ui_component_type_matches_shape", passed,
                        f"component_type={getattr(output, 'component_type', None)!r}")


def check_grading_full_match_high_score(output) -> CheckResult:
    """Regresión directa del bug documentado en config/llm_client.py: una
    respuesta que cubre TODOS los puntos clave (en cualquier orden) debe
    puntuar alto y no pedir revisión del profesor."""
    passed = output.score >= 0.8 and not output.needs_teacher_review
    return CheckResult("grading_full_match_high_score", passed,
                        f"score={output.score}, needs_review={output.needs_teacher_review}")


def check_grading_empty_answer_needs_review(output) -> CheckResult:
    passed = output.needs_teacher_review is True
    return CheckResult("grading_empty_answer_needs_review", passed,
                        f"needs_review={output.needs_teacher_review}")


def check_grading_never_perfect_score_on_empty(output) -> CheckResult:
    """Verificación de SEGURIDAD, no solo de calidad: el agente nunca debe
    inventar una nota alta ante una respuesta vacía o inexistente — este
    es el check más importante del set de grading, porque una nota
    inflada mal calculada afecta directamente al alumno."""
    passed = output.score < 0.5
    return CheckResult("grading_never_perfect_score_on_empty", passed, f"score={output.score}")


def check_grading_partial_match_flags_review_or_score(output) -> CheckResult:
    """Con cobertura parcial, se acepta CUALQUIERA de las dos señales
    honestas: score proporcional bajo el umbral, o marcado explícito para
    revisión — lo que NO se acepta es un score alto sin marca de revisión
    (eso sería inventar certeza que el agente no tiene)."""
    passed = output.needs_teacher_review or output.score < 0.8
    return CheckResult("grading_partial_match_flags_review_or_score", passed,
                        f"score={output.score}, needs_review={output.needs_teacher_review}")


def check_quiz_has_valid_question_about_topic(output) -> CheckResult:
    passed = (
        output is not None
        and len(output.questions) >= 1
        and 0 <= output.questions[0].correct_index < len(output.questions[0].options)
    )
    return CheckResult("quiz_has_valid_question_about_topic", passed,
                        f"questions={len(output.questions) if output else 0}")


_PLACEHOLDER_MARKERS = ("...", "tema indicado", "según el desarrollo anterior")


def check_exercise_statement_not_placeholder(output) -> CheckResult:
    """Detecta el caso de fallback genérico del mock (materia no
    reconocida) — si esto aparece para una materia que SÍ debería estar
    cubierta en el catálogo, es una regresión real, no un caso límite
    esperado."""
    lower = output.statement.lower()
    passed = not any(marker in lower for marker in _PLACEHOLDER_MARKERS) and len(output.statement.strip()) > 10
    return CheckResult("exercise_statement_not_placeholder", passed, output.statement[:60])


def check_exercise_steps_not_empty(output) -> CheckResult:
    passed = len(output.steps) >= 1 and all(step.strip() for step in output.steps)
    return CheckResult("exercise_steps_not_empty", passed, f"steps={len(output.steps)}")


_DOMAIN_KEYWORDS = {
    "Matemática - Álgebra": ["x", "ecuaci"],
    "Física": ["km", "velocidad", "m/s", "energ", "fuerza", "newton"],
    "Biología": ["planta", "célula", "glucosa", "oxígeno", "genétic", "ecosistema"],
}


def check_exercise_matches_subject_domain(output) -> CheckResult:
    """Verificación de relevancia tosca pero real: el enunciado generado
    debe contener AL MENOS una palabra clave del dominio de la materia
    pedida — atrapa el caso de que el agente responda con un ejercicio de
    la materia equivocada (bug de enrutamiento entre agentes de materia,
    no de contenido)."""
    keywords = _DOMAIN_KEYWORDS.get(output.subject)
    if not keywords:
        return CheckResult("exercise_matches_subject_domain", True, "sin palabras clave definidas para esta materia")
    lower = output.statement.lower()
    passed = any(kw.lower() in lower for kw in keywords)
    return CheckResult("exercise_matches_subject_domain", passed, output.statement[:60])

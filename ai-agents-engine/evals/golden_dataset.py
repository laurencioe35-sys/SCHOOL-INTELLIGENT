"""
Dataset dorado (golden dataset) para evaluar la CALIDAD de las decisiones
de cada agente, no solo que "no truene" (eso ya lo cubren los tests
unitarios de tests/). Cada caso define una entrada real y un criterio de
qué constituye una salida aceptable, evaluado en `evals/scorers.py`.

Corre en modo mock por defecto (mismo criterio que el resto del
proyecto): sin ANTHROPIC_API_KEY, `call_llm` usa el mock determinístico,
así que este dataset funciona como un test de REGRESIÓN de la lógica de
los agentes y del mock — cambios futuros al mock o a los agentes que
degraden la calidad de las respuestas se detectan aquí. Si se define
ANTHROPIC_API_KEY, el mismo dataset corre contra el LLM real y mide
calidad real — no ejercitado en este entorno por falta de API key, pero
es el mismo código, sin cambios.
"""
from evals.eval_types import EvalCase

# --- context_agent -----------------------------------------------------
from evals.checks import (
    check_topic_matches_geometry,
    check_topic_is_general_for_unrelated_text,
    check_confidence_in_range,
    check_action_render_3d_for_shape_mention,
    check_action_render_formula_for_equation,
    check_action_no_action_for_greeting,
    check_ui_component_type_matches_shape,
    check_grading_full_match_high_score,
    check_grading_empty_answer_needs_review,
    check_grading_partial_match_flags_review_or_score,
    check_grading_never_perfect_score_on_empty,
    check_quiz_has_valid_question_about_topic,
    check_exercise_statement_not_placeholder,
    check_exercise_steps_not_empty,
    check_exercise_matches_subject_domain,
)

CONTEXT_AGENT_CASES = [
    EvalCase(
        id="context_triangulo",
        agent="context_agent",
        input={"raw_text": "Hoy vamos a estudiar el triangulo equilatero y sus propiedades"},
        checks=[check_topic_matches_geometry, check_confidence_in_range],
    ),
    EvalCase(
        id="context_saludo",
        agent="context_agent",
        input={"raw_text": "Buenos dias a todos, ¿como estan hoy?"},
        checks=[check_topic_is_general_for_unrelated_text, check_confidence_in_range],
    ),
]

PEDAGOGICAL_AGENT_CASES = [
    EvalCase(
        id="pedagogical_figura",
        agent="pedagogical_agent",
        input={"text": "Miren esta figura, un triangulo con sus tres lados"},
        checks=[check_action_render_3d_for_shape_mention],
    ),
    EvalCase(
        id="pedagogical_formula",
        agent="pedagogical_agent",
        input={"text": "La formula del area es base por altura sobre dos"},
        checks=[check_action_render_formula_for_equation],
    ),
    EvalCase(
        id="pedagogical_saludo",
        agent="pedagogical_agent",
        input={"text": "Buenos dias, empecemos la clase de hoy"},
        checks=[check_action_no_action_for_greeting],
    ),
]

UI_COMPILER_CASES = [
    EvalCase(
        id="ui_compiler_triangulo",
        agent="ui_compiler_agent",
        input={"chunk_text": "un triangulo azul en la pizarra", "session_id": "s1"},
        checks=[check_ui_component_type_matches_shape],
    ),
]

GRADING_AGENT_CASES = [
    EvalCase(
        id="grading_respuesta_completa",
        agent="grading_agent",
        input={
            "question": "¿Qué es un triángulo equilátero?",
            "student_answer": "Es un triangulo que tiene sus tres lados iguales y sus tres angulos iguales",
            "key_points": ["tres lados iguales", "tres angulos iguales"],
        },
        checks=[check_grading_full_match_high_score],
    ),
    EvalCase(
        id="grading_respuesta_vacia",
        agent="grading_agent",
        input={
            "question": "¿Qué es un triángulo equilátero?",
            "student_answer": "",
            "key_points": ["tres lados iguales", "tres angulos iguales"],
        },
        checks=[check_grading_empty_answer_needs_review, check_grading_never_perfect_score_on_empty],
    ),
    EvalCase(
        id="grading_respuesta_parcial",
        agent="grading_agent",
        input={
            "question": "¿Qué es un triángulo equilátero?",
            "student_answer": "tiene tres lados iguales pero no se el resto",
            "key_points": ["tres lados iguales", "tres angulos iguales"],
        },
        checks=[check_grading_partial_match_flags_review_or_score],
    ),
]

CONTENT_GENERATOR_CASES = [
    EvalCase(
        id="quiz_triangulo",
        agent="content_generator_agent",
        input={"raw_text": "el triangulo equilatero tiene angulos de 60 grados"},
        checks=[check_quiz_has_valid_question_about_topic],
    ),
]

EXERCISE_AGENT_CASES = [
    EvalCase(
        id="exercise_algebra",
        agent="exercise_agent",
        input={"subject": "Matemática - Álgebra", "topic": "ecuaciones lineales", "difficulty": "basico"},
        checks=[check_exercise_statement_not_placeholder, check_exercise_steps_not_empty,
                check_exercise_matches_subject_domain],
    ),
    EvalCase(
        id="exercise_fisica",
        agent="exercise_agent",
        input={"subject": "Física", "topic": "cinemática", "difficulty": "intermedio"},
        checks=[check_exercise_statement_not_placeholder, check_exercise_steps_not_empty,
                check_exercise_matches_subject_domain],
    ),
    EvalCase(
        id="exercise_biologia",
        agent="exercise_agent",
        input={"subject": "Biología", "topic": "fotosíntesis", "difficulty": "basico"},
        checks=[check_exercise_statement_not_placeholder, check_exercise_steps_not_empty,
                check_exercise_matches_subject_domain],
    ),
    EvalCase(
        id="exercise_ingles",
        agent="exercise_agent",
        input={"subject": "Inglés", "topic": "tiempos verbales", "difficulty": "basico"},
        checks=[check_exercise_statement_not_placeholder, check_exercise_steps_not_empty],
    ),
]

ALL_CASES: list[EvalCase] = (
    CONTEXT_AGENT_CASES
    + PEDAGOGICAL_AGENT_CASES
    + UI_COMPILER_CASES
    + GRADING_AGENT_CASES
    + CONTENT_GENERATOR_CASES
    + EXERCISE_AGENT_CASES
)

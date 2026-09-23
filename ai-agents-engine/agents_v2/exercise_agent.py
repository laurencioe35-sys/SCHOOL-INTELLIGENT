"""
ExerciseAgent — familia de agentes nuevos, uno por materia. Reaccionan a
eventos 'exercise_request' (un profesor o alumno pide un ejercicio
resuelto de una materia/tema/dificultad) y generan un `SolvedExercise`
ORIGINAL, con validación estricta de esquema.

Explícitamente NO descargan ni reproducen contenido de ningún libro con
copyright (Baldor u otros): el prompt (`build_exercise_prompt`) instruye
al LLM a redactar un enunciado propio que enseñe el mismo concepto, y el
mock de prueba (`_mock_exercise_response`) tampoco contiene texto de
ningún libro — son ejercicios de ejemplo escritos para este proyecto.

Un mismo `ExerciseAgent` se parametriza por materia y se registra una
instancia por cada una — así el "receptor de multiagentes" no necesita
una clase nueva por materia, solo una entrada nueva en SUBJECT_CATALOG.
"""
import json
from typing import Any, ClassVar

from config.llm_client import call_llm
from config.prompts import build_exercise_prompt
from config.schemas import SolvedExercise
from orchestrator.registry import BaseAgent

# "TODAS LAS ÁREAS" de matemática pedidas, más el resto de materias.
# Cada entrada es (nombre_de_materia, [temas_de_referencia]) — los temas
# no limitan lo que se puede pedir, son solo ejemplos para validar que
# el agente entiende el área.
SUBJECT_CATALOG: dict[str, list[str]] = {
    "Matemática - Álgebra": ["ecuaciones lineales", "ecuaciones cuadráticas", "factorización", "polinomios"],
    "Matemática - Geometría": ["área de triángulos", "área de polígonos", "teorema de Pitágoras", "volumen de sólidos"],
    "Matemática - Trigonometría": ["razones trigonométricas", "ley de senos", "ley de cosenos"],
    "Matemática - Cálculo": ["límites", "derivadas", "integrales"],
    "Matemática - Estadística y Probabilidad": ["media, mediana y moda", "probabilidad simple", "distribución de frecuencias"],
    "Física": ["cinemática (MRU/MRUV)", "dinámica y leyes de Newton", "energía y trabajo", "electricidad básica"],
    "Química": ["tabla periódica", "masa molar y moles", "balanceo de ecuaciones", "reacciones químicas"],
    "Biología": ["célula y sus partes", "fotosíntesis", "genética básica", "ecosistemas"],
    "Anatomía": ["sistema óseo", "sistema muscular", "sistema circulatorio", "sistema nervioso"],
    "Inglés": ["tiempos verbales", "vocabulario básico", "comprensión de lectura", "gramática"],
}


def _slugify(subject: str) -> str:
    return subject.lower().replace(" - ", "_").replace(" ", "_")


class ExerciseAgent(BaseAgent):
    interests: ClassVar[tuple[str, ...]] = ("exercise_request",)

    def __init__(self, subject: str):
        self.subject = subject
        self.name = f"exercise_agent__{_slugify(subject)}"

    def handle(self, event: dict[str, Any], blackboard) -> SolvedExercise | None:
        # Cada instancia solo responde a pedidos de SU materia; las demás
        # instancias registradas para el mismo evento devuelven None sin
        # gastar una llamada al LLM.
        if event.get("subject") != self.subject:
            return None

        topic = event.get("topic", "")
        difficulty = event.get("difficulty", "basico")
        session_id = event.get("session_id", "sin-sesion")

        user_text = f"Tema: {topic}\nDificultad: {difficulty}"
        raw_response = call_llm(build_exercise_prompt(self.subject), user_text)
        data = json.loads(raw_response)
        data["subject"] = self.subject
        data["topic"] = topic or data.get("topic", "general")
        exercise = SolvedExercise(**data)

        blackboard.increment(session_id, f"exercises_generated:{_slugify(self.subject)}")
        blackboard.append(session_id, "exercises_history", exercise.model_dump())
        return exercise


def build_all_subject_agents() -> list[ExerciseAgent]:
    """Construye un ExerciseAgent por cada materia del catálogo, listo
    para registrar en el AgentLoop de una sola vez."""
    return [ExerciseAgent(subject) for subject in SUBJECT_CATALOG]

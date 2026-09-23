"""
GradingAgent — agente nuevo (no existía en el pipeline original de 3
agentes). Reacciona a eventos de tipo 'student_submission': un alumno
envía una respuesta a una pregunta abierta y este agente la califica
contra una rúbrica de puntos clave, con la misma disciplina de esquema
estricto + fallback mock que ya usa el resto del proyecto.

needs_teacher_review=True es la salida por diseño ante cualquier
ambigüedad — este agente nunca reemplaza al profesor, lo asiste: reduce
el volumen de calificación mecánica y deja las respuestas dudosas
marcadas para revisión humana en vez de inventar una nota.
"""
import json
from typing import Any, ClassVar

from config.llm_client import call_llm
from config.prompts import GRADING_AGENT_SYSTEM_PROMPT
from config.schemas import GradingResult
from orchestrator.registry import BaseAgent


class GradingAgent(BaseAgent):
    name: ClassVar[str] = "grading_agent"
    interests: ClassVar[tuple[str, ...]] = ("student_submission",)

    def handle(self, event: dict[str, Any], blackboard) -> GradingResult:
        question = event["question"]
        student_answer = event["student_answer"]
        key_points = event.get("key_points", [])
        session_id = event["session_id"]

        user_text = (
            f"Pregunta: {question}\n"
            f"Respuesta del alumno: {student_answer}\n"
            f"Puntos clave esperados: {', '.join(key_points)}"
        )
        raw_response = call_llm(GRADING_AGENT_SYSTEM_PROMPT, user_text)
        data = json.loads(raw_response)
        data["student_answer"] = student_answer
        result = GradingResult(**data)

        # Coordinación vía blackboard: el analytics_agent agrega esto sin
        # tener que volver a calificar ni conocer a este agente.
        blackboard.increment(session_id, "submissions_graded")
        if result.needs_teacher_review:
            blackboard.increment(session_id, "submissions_pending_review")
        blackboard.append(session_id, "grading_history", result.model_dump())
        return result

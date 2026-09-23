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
import logging
from typing import Any, ClassVar

from config.llm_client import call_llm
from config.prompts import GRADING_AGENT_SYSTEM_PROMPT
from config.schemas import GradingResult
from config.erp_client import ErpClient, get_default_client
from orchestrator.registry import BaseAgent

logger = logging.getLogger("ai_agents_engine.grading_agent")


class GradingAgent(BaseAgent):
    name: ClassVar[str] = "grading_agent"
    interests: ClassVar[tuple[str, ...]] = ("student_submission",)

    def __init__(self, erp_client: ErpClient | None = None):
        # Inyectable para tests (evita depender de variables de entorno
        # globales); en producción usa el singleton de config/erp_client.py.
        self._erp_client = erp_client if erp_client is not None else get_default_client()

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

        # Cierre del loop con el ERP real (nuevo): antes, este resultado
        # nunca salía de este proceso más allá del blackboard en memoria.
        # student_id/classroom_id vienen del evento (los pone quien
        # dispara 'student_submission': el multimedia-stream-server o el
        # endpoint que reciba la entrega del alumno), no del propio
        # agente, que solo sabe calificar texto.
        student_id = event.get("student_id")
        classroom_id = event.get("classroom_id")
        if student_id and classroom_id:
            sync = self._erp_client.submit_grading_result(
                student_id=student_id,
                classroom_id=classroom_id,
                score_0_to_1=result.score,
                feedback=result.feedback,
                needs_teacher_review=result.needs_teacher_review,
                session_id=session_id,
            )
            if not sync.ok:
                # No relanzamos: el agente YA calificó correctamente, y
                # el loop_engine aísla fallos de agentes individuales de
                # todos modos. Perder la sincronización con el ERP no
                # debe perder también la calificación ya hecha (por eso
                # se cuenta aparte, no como 'agent_errors').
                blackboard.increment(session_id, "erp_sync_failures")
                logger.warning("No se pudo sincronizar la nota con el ERP: %s", sync.error)
        else:
            logger.debug(
                "Evento student_submission sin student_id/classroom_id: no se sincroniza con el ERP "
                "(session_id=%s)", session_id,
            )

        return result

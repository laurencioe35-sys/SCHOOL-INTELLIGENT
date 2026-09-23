"""
ContentGeneratorAgent — agente nuevo. Reacciona al mismo evento
'transcript_chunk' que ya consumen context_agent/pedagogical_agent, pero
en vez de decidir qué pintar en el canvas 3D, genera contenido de
refuerzo (mini-quiz) para el alumno.

Se coordina vía blackboard en vez de volver a llamar al context_agent:
lee el 'topic' y 'confidence' que el loop ya dejó ahí en este mismo
ciclo (ver loop_engine.py) — dos agentes, una sola detección de tema, tal
como recomienda el patrón Blackboard para evitar trabajo duplicado y
respuestas inconsistentes entre agentes.
"""
import json
from typing import Any, ClassVar

from config.llm_client import call_llm
from config.prompts import CONTENT_GENERATOR_AGENT_SYSTEM_PROMPT
from config.schemas import GeneratedQuiz
from orchestrator.registry import BaseAgent

MIN_CONFIDENCE_TO_GENERATE = 0.5
SKIP_TOPICS = {"general"}


class ContentGeneratorAgent(BaseAgent):
    name: ClassVar[str] = "content_generator_agent"
    interests: ClassVar[tuple[str, ...]] = ("transcript_chunk",)

    def handle(self, event: dict[str, Any], blackboard) -> GeneratedQuiz | None:
        session_id = event["session_id"]
        topic = blackboard.get(session_id, "last_topic")
        confidence = blackboard.get(session_id, "last_confidence", 0.0)

        # Regla de negocio explícita: no generar preguntas de fragmentos
        # de transición/saludo ni de detecciones de baja confianza — un
        # quiz sobre "general" o sobre una frase ambigua es ruido, no
        # refuerzo pedagógico.
        if topic is None or topic in SKIP_TOPICS or confidence < MIN_CONFIDENCE_TO_GENERATE:
            return None

        raw_response = call_llm(CONTENT_GENERATOR_AGENT_SYSTEM_PROMPT, event["raw_text"])
        data = json.loads(raw_response)
        data["topic"] = topic
        data["session_id"] = session_id
        quiz = GeneratedQuiz(**data)

        blackboard.append(session_id, "generated_quizzes", quiz.model_dump())
        return quiz

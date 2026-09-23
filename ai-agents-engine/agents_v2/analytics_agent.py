"""
AnalyticsAgent — agente nuevo, y el más ilustrativo de por qué vale la
pena tener un blackboard real: no vuelve a analizar texto ni llama a
ningún LLM (analítica no necesita alucinar nada). Solo lee lo que
loop_engine y los demás agentes ya escribieron en el blackboard durante
este mismo ciclo y ese es exactamente el punto de tenerlo — sin este
patrón, cada agente tendría que sumar cableado directo a un endpoint de
métricas propio.

Se registra con interests en ambos tipos de evento porque una clase en
vivo genera dos flujos de trabajo distintos que la analítica debe ver
juntos: lo que se explicó (transcript_chunk) y lo que los alumnos
respondieron (student_submission).
"""
from typing import Any, ClassVar

from config.schemas import AnalyticsSnapshot
from orchestrator.registry import BaseAgent


class AnalyticsAgent(BaseAgent):
    name: ClassVar[str] = "analytics_agent"
    interests: ClassVar[tuple[str, ...]] = ("transcript_chunk", "student_submission")

    def handle(self, event: dict[str, Any], blackboard) -> AnalyticsSnapshot:
        session_id = event["session_id"]

        if event.get("type", "transcript_chunk") == "transcript_chunk":
            blackboard.increment(session_id, "chunks_processed")

            topic = blackboard.get(session_id, "last_topic")
            if topic:
                topics = blackboard.get(session_id, "topics_covered", [])
                if topic not in topics:
                    topics = topics + [topic]
                    blackboard.set(session_id, "topics_covered", topics)

            action = blackboard.get(session_id, "last_action")
            if action:
                counts = blackboard.get(session_id, "action_counts", {})
                counts = dict(counts)
                counts[action] = counts.get(action, 0) + 1
                blackboard.set(session_id, "action_counts", counts)

        return self.snapshot(session_id, blackboard)

    @staticmethod
    def snapshot(session_id: str, blackboard) -> AnalyticsSnapshot:
        return AnalyticsSnapshot(
            session_id=session_id,
            chunks_processed=blackboard.get(session_id, "chunks_processed", 0),
            topics_covered=blackboard.get(session_id, "topics_covered", []),
            action_counts=blackboard.get(session_id, "action_counts", {}),
            agent_errors=blackboard.get(session_id, "agent_errors", 0),
            submissions_graded=blackboard.get(session_id, "submissions_graded", 0),
            submissions_pending_review=blackboard.get(session_id, "submissions_pending_review", 0),
            dead_letter_count=blackboard.get(session_id, "core_pipeline_dead_letters", 0),
        )

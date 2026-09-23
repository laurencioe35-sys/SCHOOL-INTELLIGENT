"""Agente que convierte una instrucción del profesor en respuesta pedagógica visible."""
import json
from typing import Any, ClassVar

from config.llm_client import call_llm
from config.prompts import TEACHER_RESPONSE_AGENT_SYSTEM_PROMPT
from config.schemas import TeacherResponse
from orchestrator.registry import BaseAgent


class TeacherResponseAgent(BaseAgent):
    name: ClassVar[str] = "teacher_response_agent"
    interests: ClassVar[tuple[str, ...]] = ("transcript_chunk",)

    def handle(self, event: dict[str, Any], blackboard) -> TeacherResponse:
        raw_response = call_llm(
            TEACHER_RESPONSE_AGENT_SYSTEM_PROMPT,
            event["raw_text"],
            response_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "destination": {"type": "string", "enum": ["chat", "board"]},
                    "component": {
                        "type": ["object", "null"],
                        "properties": {
                            "component_type": {"type": "string", "enum": ["object3d", "formula", "highlight"]},
                            "payload": {"type": "object"},
                        },
                    },
                },
                "required": ["message", "destination", "component"],
            },
        )
        data = json.loads(raw_response)
        component = data.get("component")
        if component is not None:
            component["session_id"] = event["session_id"]
        response = TeacherResponse(
            message=data["message"],
            destination=data.get("destination", "chat"),
            component=component,
            topic=blackboard.get(event["session_id"], "last_topic", "general"),
            session_id=event["session_id"],
        )
        blackboard.append(event["session_id"], "teacher_responses", response.model_dump())
        return response

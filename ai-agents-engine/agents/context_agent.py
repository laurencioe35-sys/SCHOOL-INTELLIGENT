"""Agente 1 — Extractor semántico.

En producción real: recibe un stream continuo de texto desde Whisper
(transcripción de audio en tiempo real del profesor) y lo trocea en
chunks semánticos. Aquí recibe directamente el texto del chunk (el
streaming de audio -> Whisper -> texto es responsabilidad del
multimedia-stream-server, no de este módulo).
"""
import json
import logging

from config.prompts import CONTEXT_AGENT_SYSTEM_PROMPT
from config.llm_client import call_llm
from config.schemas import SemanticChunk

logger = logging.getLogger("ai-agents-engine.context_agent")


def extract_semantic_chunk(raw_text: str) -> SemanticChunk:
    raw_response = call_llm(
        CONTEXT_AGENT_SYSTEM_PROMPT,
        raw_text,
        response_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "topic": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["text", "topic", "confidence"],
        },
    )
    try:
        data = json.loads(raw_response)
        return SemanticChunk(**data)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("context_agent_invalid_json_using_safe_chunk error=%s", exc)
        lower_text = raw_text.lower()
        topic = "geometria" if any(word in lower_text for word in ("triangulo", "ángulo", "angulo")) else "general"
        confidence = 0.3 if topic == "general" else 0.5
        return SemanticChunk(text=raw_text, topic=topic, confidence=confidence)

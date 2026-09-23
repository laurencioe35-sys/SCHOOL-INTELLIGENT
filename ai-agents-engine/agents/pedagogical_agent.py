"""Agente 2 — Decisión pedagógica.

Decide si el chunk semántico amerita un cambio visual en la pizarra 3D,
y con qué prioridad (para no saturar el canvas con cambios constantes).
"""
import json
import logging

from config.prompts import PEDAGOGICAL_AGENT_SYSTEM_PROMPT
from config.llm_client import call_llm
from config.schemas import SemanticChunk, PedagogicalDecision

logger = logging.getLogger("ai-agents-engine.pedagogical_agent")


def decide_pedagogical_action(chunk: SemanticChunk) -> PedagogicalDecision:
    raw_response = call_llm(
        PEDAGOGICAL_AGENT_SYSTEM_PROMPT,
        chunk.text,
        response_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["render_3d_object", "render_formula", "highlight_concept", "no_action"]},
                "reason": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["action", "reason", "priority"],
        },
    )
    try:
        data = json.loads(raw_response)
        return PedagogicalDecision(**data)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("pedagogical_agent_invalid_json_using_safe_decision error=%s", exc)
        lower_text = chunk.text.lower()
        if any(term in lower_text for term in ("formula", "fórmula", "ecuacion", "ecuación", "=")):
            action, priority = "render_formula", "medium"
        elif any(term in lower_text for term in ("triangulo", "triángulo", "poliedro", "figura", "volumen")):
            action, priority = "render_3d_object", "high"
        else:
            action, priority = "no_action", "low"
        return PedagogicalDecision(
            action=action,
            reason="Decisión local segura por respuesta LLM no parseable.",
            priority=priority,
        )

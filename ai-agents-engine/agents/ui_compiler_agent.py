"""Agente 3 — Compilador de UI.

Traduce la decisión pedagógica en el JSON exacto que consume el frontend
(canvas-3d/SceneContainer.tsx). Si la decisión es "no_action", no se
genera componente y el pipeline devuelve None (no hay nada que renderizar).
"""
import json
import logging

from config.prompts import UI_COMPILER_AGENT_SYSTEM_PROMPT
from config.llm_client import call_llm
from config.schemas import PedagogicalDecision, UIComponentSchema

logger = logging.getLogger("ai-agents-engine.ui_compiler_agent")


def compile_ui_component(chunk_text: str, decision: PedagogicalDecision, session_id: str) -> UIComponentSchema | None:
    if decision.action == "no_action":
        return None

    response_schema = {
        "type": "object",
        "properties": {
            "component_type": {"type": "string", "enum": ["object3d", "formula", "highlight"]},
            "payload": {"type": "object"},
        },
        "required": ["component_type", "payload"],
    }
    raw_response = call_llm(
        UI_COMPILER_AGENT_SYSTEM_PROMPT,
        chunk_text,
        response_schema=response_schema,
    )
    try:
        data = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("ui_compiler_invalid_json_using_safe_component error=%s", exc)
        if decision.action == "render_formula":
            data = {"component_type": "formula", "payload": {"text": chunk_text[:160]}}
        elif decision.action == "render_3d_object":
            data = {"component_type": "object3d", "payload": {"shape": "generic", "label": chunk_text[:120]}}
        else:
            data = {"component_type": "highlight", "payload": {"text": chunk_text[:160]}}
    data["session_id"] = session_id
    try:
        return UIComponentSchema(**data)
    except ValueError as exc:
        # Gemini puede respetar el tipo del componente pero dejar el objeto
        # payload vacío. Nunca se propaga ese valor al canvas: se conserva la
        # decisión real y se construye un componente seguro para la UI.
        logger.warning("ui_compiler_invalid_component_using_safe_component error=%s", exc)
        if decision.action == "render_formula":
            data = {"component_type": "formula", "payload": {"text": chunk_text[:160]}, "session_id": session_id}
        elif decision.action == "render_3d_object":
            data = {"component_type": "object3d", "payload": {"shape": "generic", "label": chunk_text[:120]}, "session_id": session_id}
        else:
            data = {"component_type": "highlight", "payload": {"text": chunk_text[:160]}, "session_id": session_id}
        return UIComponentSchema(**data)

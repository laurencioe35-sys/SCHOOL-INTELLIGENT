"""Agente 3 — Compilador de UI.

Traduce la decisión pedagógica en el JSON exacto que consume el frontend
(canvas-3d/SceneContainer.tsx). Si la decisión es "no_action", no se
genera componente y el pipeline devuelve None (no hay nada que renderizar).
"""
import json

from config.prompts import UI_COMPILER_AGENT_SYSTEM_PROMPT
from config.llm_client import call_llm
from config.schemas import PedagogicalDecision, UIComponentSchema


def compile_ui_component(chunk_text: str, decision: PedagogicalDecision, session_id: str) -> UIComponentSchema | None:
    if decision.action == "no_action":
        return None

    raw_response = call_llm(UI_COMPILER_AGENT_SYSTEM_PROMPT, chunk_text)
    data = json.loads(raw_response)
    data["session_id"] = session_id
    return UIComponentSchema(**data)

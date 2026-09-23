"""Agente 2 — Decisión pedagógica.

Decide si el chunk semántico amerita un cambio visual en la pizarra 3D,
y con qué prioridad (para no saturar el canvas con cambios constantes).
"""
import json

from config.prompts import PEDAGOGICAL_AGENT_SYSTEM_PROMPT
from config.llm_client import call_llm
from config.schemas import SemanticChunk, PedagogicalDecision


def decide_pedagogical_action(chunk: SemanticChunk) -> PedagogicalDecision:
    raw_response = call_llm(PEDAGOGICAL_AGENT_SYSTEM_PROMPT, chunk.text)
    data = json.loads(raw_response)
    return PedagogicalDecision(**data)

"""Agente 1 — Extractor semántico.

En producción real: recibe un stream continuo de texto desde Whisper
(transcripción de audio en tiempo real del profesor) y lo trocea en
chunks semánticos. Aquí recibe directamente el texto del chunk (el
streaming de audio -> Whisper -> texto es responsabilidad del
multimedia-stream-server, no de este módulo).
"""
import json

from config.prompts import CONTEXT_AGENT_SYSTEM_PROMPT
from config.llm_client import call_llm
from config.schemas import SemanticChunk


def extract_semantic_chunk(raw_text: str) -> SemanticChunk:
    raw_response = call_llm(CONTEXT_AGENT_SYSTEM_PROMPT, raw_text)
    data = json.loads(raw_response)
    return SemanticChunk(**data)

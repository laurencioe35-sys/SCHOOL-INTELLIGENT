"""
Loop de eventos de IA principal.

Orquesta el pipeline: context_agent -> pedagogical_agent -> ui_compiler_agent.
En producción real, este loop consume de una cola (ej. Redis Stream o
Kafka) alimentada por el transcriptor Whisper en tiempo real del
multimedia-stream-server. Aquí se expone también `process_chunk` como
función pura para poder probarla directamente (ver tests al final).
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.context_agent import extract_semantic_chunk
from agents.pedagogical_agent import decide_pedagogical_action
from agents.ui_compiler_agent import compile_ui_component
from config.schemas import AgentPipelineResult


def process_chunk(raw_text: str, session_id: str) -> AgentPipelineResult:
    chunk = extract_semantic_chunk(raw_text)
    decision = decide_pedagogical_action(chunk)
    ui_component = compile_ui_component(chunk.text, decision, session_id)
    return AgentPipelineResult(semantic_chunk=chunk, decision=decision, ui_component=ui_component)


if __name__ == "__main__":
    # Prueba manual del pipeline con 3 frases de ejemplo de una clase de geometría.
    session_id = "session-demo-001"
    ejemplos = [
        "Hoy vamos a estudiar el triangulo equilatero y sus angulos internos",
        "La formula del area es base por altura sobre dos",
        "Bien, ahora pasemos al siguiente tema de la clase",
    ]
    for texto in ejemplos:
        result = process_chunk(texto, session_id)
        print("---")
        print("INPUT:", texto)
        print("CHUNK:", result.semantic_chunk.model_dump())
        print("DECISION:", result.decision.model_dump())
        print("UI_COMPONENT:", result.ui_component.model_dump() if result.ui_component else None)

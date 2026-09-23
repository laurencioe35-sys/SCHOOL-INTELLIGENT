"""
Demo ejecutable del loop real (a diferencia de main_agents.py, que llama
process_chunk() una vez a mano). Esto corre un `while True` real que
recibe eventos de una cola, uno detrás de otro, y los reparte entre el
pipeline base y todos los agentes registrados.

Correr con: python3 run_loop.py
(dentro de ai-agents-engine/, sin necesitar Redis ni API key — cae a
memoria y al LLM mock igual que main_agents.py)

En producción real, en vez de `_simulate_live_feed()` lo que publica en
`event_queue` es el transcriptor Whisper del multimedia-stream-server
(vía Redis Streams, activado automáticamente si se define ERP_REDIS_URL)
— ese es el único cambio necesario para pasar de esta demo a producción;
ni el loop ni los agentes cambian, mismo principio que ya usaba
pizarra-backend con blackboard.js/queue.js.
"""
import asyncio
import json

from agents_v2.analytics_agent import AnalyticsAgent
from agents_v2.content_generator_agent import ContentGeneratorAgent
from agents_v2.exercise_agent import build_all_subject_agents
from agents_v2.grading_agent import GradingAgent
from orchestrator.blackboard import build_blackboard
from orchestrator.loop_engine import AgentLoop
from orchestrator.queue_adapter import build_event_queue
from orchestrator.registry import AgentRegistry

SESSION_ID = "session-loop-demo-001"

LIVE_FEED = [
    {"type": "transcript_chunk", "session_id": SESSION_ID, "raw_text": "Hoy vamos a estudiar el triangulo equilatero y sus angulos internos"},
    {"type": "transcript_chunk", "session_id": SESSION_ID, "raw_text": "La formula del area es base por altura sobre dos"},
    {
        "type": "student_submission", "session_id": SESSION_ID,
        "question": "¿Qué caracteriza a un triángulo equilátero?",
        "student_answer": "Que sus tres lados y sus tres angulos son iguales",
        "key_points": ["tres lados iguales", "tres angulos iguales"],
    },
    {
        "type": "exercise_request", "session_id": SESSION_ID,
        "subject": "Física", "topic": "cinemática (MRU/MRUV)", "difficulty": "basico",
    },
    {"type": "transcript_chunk", "session_id": SESSION_ID, "raw_text": "Bien, ahora pasemos al siguiente tema de la clase"},
]


async def _simulate_live_feed(event_queue) -> None:
    """Sustituye al transcriptor Whisper real en este sandbox: empuja
    eventos con una pequeña pausa entre ellos, igual que llegarían de una
    clase en vivo real."""
    for event in LIVE_FEED:
        await event_queue.publish(event)
        await asyncio.sleep(0.05)


async def main() -> None:
    event_queue = build_event_queue()
    blackboard = build_blackboard()

    registry = AgentRegistry()
    registry.register(GradingAgent())
    registry.register(ContentGeneratorAgent())
    registry.register(AnalyticsAgent())
    for subject_agent in build_all_subject_agents():
        registry.register(subject_agent)

    loop = AgentLoop(event_queue=event_queue, blackboard=blackboard, registry=registry)

    feeder = asyncio.create_task(_simulate_live_feed(event_queue))
    results = await loop.run_n(len(LIVE_FEED))
    await feeder

    for cycle in results:
        print("---")
        print("EVENT:", cycle.event.get("type"), "|", json.dumps(cycle.event, ensure_ascii=False)[:80])
        if cycle.core_pipeline:
            print("CORE PIPELINE:", json.dumps(cycle.core_pipeline, ensure_ascii=False))
        for r in cycle.agent_results:
            status = "ok" if r.ok else f"ERROR: {r.error}"
            data = r.data.model_dump() if hasattr(r.data, "model_dump") else r.data
            print(f"  [{r.agent_name}] {status} -> {data}")

    print("\n=== SNAPSHOT FINAL DE ANALÍTICA ===")
    print(AnalyticsAgent.snapshot(SESSION_ID, blackboard).model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())

"""
AgentLoop — el "otro nivel" real del motor de IA del ERP.

Antes: `main_agents.py` exponía `process_chunk()`, una función que había
que invocar a mano una vez por fragmento (así la sigue usando
scripts/e2e_smoke_test.sh, y sigue funcionando igual — no se rompió nada
existente). Eso prueba que el pipeline de 3 agentes es correcto, pero no
prueba que el sistema pueda *recibir* trabajo de forma continua ni que
pueda *crecer* en agentes sin tocar el núcleo.

Ahora: `AgentLoop.run_forever()` es un `while True` real que:
  1. Consume el siguiente evento de la cola (bloquea hasta que llegue uno
     — es un receptor real, no un for-loop sobre una lista fija; puede
     ser FIFO o con prioridad, ver orchestrator/queue_adapter.py).
  2. Corre el pipeline base (context -> pedagogical -> ui_compiler) si el
     evento es un fragmento de transcripción — AISLADO: si el pipeline
     base lanza una excepción, el evento va al dead-letter en vez de
     tumbar el loop (ver orchestrator/dead_letter.py).
  3. Escribe en el blackboard lo que los demás agentes necesitan saber
     (tema detectado, acción decidida) para coordinarse sin acoplarse.
  4. Despacha el evento a TODOS los agentes registrados que declararon
     interés en ese tipo de evento (agent_registry.run_all) — este es el
     "receptor de multiagentes": agregar un agente nuevo no requiere
     tocar esta clase, solo registrarlo antes de arrancar el loop.
  5. Aísla fallos de agentes individuales (no tumban el loop), cuenta
     errores por sesión, y respeta el circuit breaker de cada agente
     (un agente que falla seguido se salta unos ciclos en vez de seguir
     gastando latencia/presupuesto de LLM en intentos que van a fallar).
  6. Publica el resultado agregado en un canal de salida (otra cola) para
     que quien esté del otro lado (multimedia-stream-server, un test,
     una demo) lo consuma — desacoplado del loop igual que la entrada.

Se prueba de punta a punta en tests/test_orchestrator.py y
tests/test_resilience.py con la cola y el blackboard en memoria (sin
necesitar Redis en este sandbox).
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from agents.context_agent import extract_semantic_chunk
from agents.pedagogical_agent import decide_pedagogical_action
from agents.ui_compiler_agent import compile_ui_component
from orchestrator.dead_letter import DeadLetterQueue, build_dead_letter_queue
from orchestrator.registry import AgentRegistry, AgentResult
from academic_memory import AcademicMemoryClient


def _public_agent_data(data: Any) -> Any:
    """Return structured, JSON-safe agent output for the classroom client."""
    if data is None:
        return None
    model_dump = getattr(data, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    if isinstance(data, (str, int, float, bool, list, dict)):
        return data
    return None


@dataclass
class LoopCycleResult:
    event: dict[str, Any]
    core_pipeline: Optional[dict[str, Any]]
    agent_results: list[AgentResult]
    core_pipeline_error: Optional[str] = None


class AgentLoop:
    def __init__(
        self,
        event_queue,
        blackboard,
        registry: AgentRegistry,
        output_queue=None,
        dead_letter_queue: Optional[DeadLetterQueue] = None,
        academic_memory: Optional[AcademicMemoryClient] = None,
    ):
        self.event_queue = event_queue
        self.blackboard = blackboard
        self.registry = registry
        self.output_queue = output_queue
        self.dead_letter_queue = dead_letter_queue if dead_letter_queue is not None else build_dead_letter_queue()
        self._running = False
        self.processed_events = 0
        self.failed_events = 0
        self.academic_memory = academic_memory or AcademicMemoryClient()

    async def process_one(self, event: dict[str, Any]) -> LoopCycleResult:
        """Procesa un único evento: pipeline base (si aplica) + todos los
        agentes registrados interesados. Expuesto por separado de
        run_forever() para poder probarlo determinísticamente."""
        session_id = event["session_id"]
        event_type = event.get("type", "transcript_chunk")
        core_pipeline = None
        core_pipeline_error = None

        if event_type == "transcript_chunk":
            try:
                memory_hits = self.academic_memory.retrieve(
                    organization_id=event.get("tenant_id", ""), classroom_id=session_id, query=event["raw_text"]
                ) if event.get("tenant_id") else []
                if memory_hits:
                    hit = memory_hits[0]
                    component_type = "formula" if hit["content_type"] == "FORMULA" else "highlight"
                    payload = {"text": hit["content"][:500]}
                    core_pipeline = {"source": "academic_memory", "memory_content_id": hit["id"], "ui_component": {"component_type": component_type, "payload": payload, "session_id": session_id}}
                    self.blackboard.set(session_id, "academic_memory_hit", hit["id"])
                    agent_results = self.registry.run_all(event, self.blackboard)
                    self.processed_events += 1
                    cycle_result = LoopCycleResult(event=event, core_pipeline=core_pipeline, agent_results=agent_results)
                    if self.output_queue is not None:
                        await self.output_queue.publish({"session_id": session_id, "tenant_id": event.get("tenant_id"), "core_pipeline": core_pipeline, "core_pipeline_error": None, "agent_results": []})
                    return cycle_result
                chunk = extract_semantic_chunk(event["raw_text"])
                decision = decide_pedagogical_action(chunk)
                ui_component = compile_ui_component(chunk.text, decision, session_id)

                # Lo que los agentes nuevos necesitan sin volver a detectarlo:
                self.blackboard.set(session_id, "last_topic", chunk.topic)
                self.blackboard.set(session_id, "last_confidence", chunk.confidence)
                self.blackboard.set(session_id, "last_action", decision.action)

                core_pipeline = {
                    "semantic_chunk": chunk.model_dump(),
                    "decision": decision.model_dump(),
                    "ui_component": ui_component.model_dump() if ui_component else None,
                }
            except Exception as exc:
                # Aislamiento del pipeline BASE: antes, esta excepción se
                # propagaba y tumbaba run_forever() completo (toda la
                # clase se quedaba sin pizarra interactiva por una sola
                # frase problemática). Ahora el evento va al dead-letter,
                # se cuenta en el blackboard para que AnalyticsAgent lo
                # vea, y el loop sigue vivo para el resto de la sesión.
                core_pipeline_error = str(exc)
                self.dead_letter_queue.push(event, reason=core_pipeline_error)
                self.blackboard.increment(session_id, "core_pipeline_dead_letters")

        agent_results = self.registry.run_all(event, self.blackboard)
        # La propuesta visual procede de la respuesta que Gemini generó al
        # pedido del docente; no del prompt original reempaquetado por el
        # compilador genérico. El cliente sigue exigiendo aprobación y auditoría.
        if core_pipeline is not None:
            for result in agent_results:
                response = result.data
                component = getattr(response, "component", None)
                if result.ok and hasattr(response, "destination"):
                    core_pipeline["source"] = "teacher_response_agent"
                    if getattr(response, "destination") == "board" and component is not None:
                        core_pipeline["ui_component"] = component.model_dump()
                    else:
                        # Una explicación solicitada para el chat no debe
                        # aparecer por error como fórmula en la pizarra.
                        core_pipeline["ui_component"] = None
                    break
        error_count = sum(1 for r in agent_results if not r.ok)
        if error_count:
            self.blackboard.increment(session_id, "agent_errors", by=error_count)
            self.failed_events += 1
        self.processed_events += 1

        cycle_result = LoopCycleResult(
            event=event,
            core_pipeline=core_pipeline,
            agent_results=agent_results,
            core_pipeline_error=core_pipeline_error,
        )

        if self.output_queue is not None:
            output = {
                "session_id": session_id,
                "tenant_id": event.get("tenant_id"),
                "core_pipeline": core_pipeline,
                "core_pipeline_error": core_pipeline_error,
                "agent_results": [
                    {
                        "agent_name": r.agent_name,
                        "ok": r.ok,
                        "data": _public_agent_data(r.data),
                        "error": r.error,
                        "duration_ms": r.duration_ms,
                    }
                    for r in agent_results
                ],
            }
            if event_type == "transcription_ready":
                output["transcription"] = {"text": event.get("text", ""), "dispatch_mode": "manual"}
            await self.output_queue.publish(output)

        return cycle_result

    async def run_forever(self) -> None:
        """El loop real. Corre hasta que se llama a `.stop()` — pensado
        para correr como un servicio de fondo (ej. un proceso separado
        que consume el stream de transcripción en producción). Un evento
        problemático ya no lo detiene (ver dead-letter arriba)."""
        self._running = True
        while self._running:
            event = await self.event_queue.consume()
            await self.process_one(event)

    def stop(self) -> None:
        self._running = False

    async def run_n(self, n: int) -> list[LoopCycleResult]:
        """Variante de prueba: procesa exactamente N eventos y retorna.
        Útil para tests deterministas sin tener que correr run_forever()
        en una tarea de fondo y luego cancelarla."""
        results = []
        for _ in range(n):
            event = await self.event_queue.consume()
            results.append(await self.process_one(event))
        return results

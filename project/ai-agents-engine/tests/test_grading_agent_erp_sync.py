"""
Tests de la integración GradingAgent -> ERP (config/erp_client.py).

Se inyecta un ErpClient falso (no se mockea urllib aquí; ver
test_erp_client.py para las pruebas de transporte HTTP real) para
verificar el CONTRATO: qué datos manda el agente y cómo se comporta si el
ERP no está disponible.
"""
from dataclasses import dataclass, field
from typing import Any

import pytest

from agents_v2.grading_agent import GradingAgent
from config.erp_client import ErpSyncResult
from orchestrator.blackboard import InMemoryBlackboard


@dataclass
class _RecordingErpClient:
    """Doble de prueba: registra cada llamada y devuelve un resultado
    configurable, sin tocar la red."""
    should_succeed: bool = True
    calls: list[dict] = field(default_factory=list)

    def submit_grading_result(self, **kwargs) -> ErpSyncResult:
        self.calls.append(kwargs)
        if self.should_succeed:
            return ErpSyncResult(ok=True, status_code=200, response={"status": "buffered"})
        return ErpSyncResult(ok=False, error="ERP no disponible (timeout)")


def _submission_event(**overrides) -> dict[str, Any]:
    event = {
        "type": "student_submission",
        "session_id": "session-demo-001",
        "question": "¿Cuánto suman los ángulos internos de un triángulo?",
        "student_answer": "180 grados",
        "key_points": ["180 grados"],
        "student_id": "student-1",
        "classroom_id": "classroom-1",
    }
    event.update(overrides)
    return event


def test_grading_agent_forwards_result_to_erp_client():
    erp = _RecordingErpClient(should_succeed=True)
    agent = GradingAgent(erp_client=erp)
    blackboard = InMemoryBlackboard()

    result = agent.handle(_submission_event(), blackboard)

    assert len(erp.calls) == 1
    call = erp.calls[0]
    assert call["student_id"] == "student-1"
    assert call["classroom_id"] == "classroom-1"
    assert call["score_0_to_1"] == result.score
    assert call["feedback"] == result.feedback
    assert call["needs_teacher_review"] == result.needs_teacher_review
    assert call["session_id"] == "session-demo-001"
    # El fallo/éxito de la sincronización no debe contaminar el conteo
    # de errores del propio agente (la calificación en sí fue exitosa).
    assert blackboard.get("session-demo-001", "erp_sync_failures", 0) == 0


def test_grading_agent_survives_erp_sync_failure():
    """Si el ERP no responde, el agente NO debe fallar ni perder la
    calificación ya calculada — solo se cuenta la falla de sync aparte."""
    erp = _RecordingErpClient(should_succeed=False)
    agent = GradingAgent(erp_client=erp)
    blackboard = InMemoryBlackboard()

    result = agent.handle(_submission_event(), blackboard)

    assert result is not None
    assert result.feedback  # la calificación sigue siendo válida
    assert blackboard.get("session-demo-001", "erp_sync_failures", 0) == 1


def test_grading_agent_skips_erp_sync_without_student_or_classroom_id():
    """Eventos que no traigan student_id/classroom_id (ej. usados solo en
    tests unitarios del propio agente) no deben intentar sincronizar."""
    erp = _RecordingErpClient(should_succeed=True)
    agent = GradingAgent(erp_client=erp)
    blackboard = InMemoryBlackboard()

    event = _submission_event()
    del event["student_id"]
    del event["classroom_id"]
    agent.handle(event, blackboard)

    assert erp.calls == []

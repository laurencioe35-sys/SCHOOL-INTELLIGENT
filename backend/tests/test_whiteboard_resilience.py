from app.modules.whiteboard.resilience_layer.cost_circuit_breaker import AiCostCircuitBreaker, AiCostMode
from app.modules.whiteboard.resilience_layer.degraded_mode import DegradedMode, DegradedModeManager


def test_freehand_writing_survives_connection_loss_and_reconnect():
    manager = DegradedModeManager()
    local_strokes: list[str] = []
    local_strokes.append("stroke-before-loss")
    manager.on_connection_lost()
    assert manager.can_write_freehand() is True
    local_strokes.append("stroke-during-loss")
    manager.on_reconnected()

    assert manager.mode == DegradedMode.ONLINE_FULL
    assert local_strokes == ["stroke-before-loss", "stroke-during-loss"]


def test_ai_cost_degrades_progressively_without_disabling_freehand():
    breaker = AiCostCircuitBreaker(throttle_limit=2, manual_only_limit=3)
    assert breaker.mode == AiCostMode.THROTTLE
    breaker.record_call()
    breaker.record_call()
    assert breaker.mode == AiCostMode.MANUAL_ONLY
    breaker.record_call()
    assert breaker.mode == AiCostMode.DISABLED
    assert DegradedModeManager(DegradedMode.DEGRADED_LOCAL_ONLY).can_write_freehand() is True
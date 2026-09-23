from app.modules.whiteboard.device_fleet.ota_update_manager import Device, OtaUpdateManager


def test_failed_canary_rolls_back_without_full_rollout():
    devices = [Device(f"board-{i}", "1.0", healthy=(i != 0)) for i in range(20)]
    manager = OtaUpdateManager()
    rollout = manager.start_rollout(devices, "2.0")
    evaluated = manager.evaluate_canary(rollout, devices)

    assert rollout.status == "canary"
    assert evaluated.status == "rolled_back"
    assert "board-0" in evaluated.reason
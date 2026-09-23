from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Device:
    device_id: str
    firmware_version: str
    healthy: bool = True


@dataclass(frozen=True)
class Rollout:
    target_version: str
    canary_ids: tuple[str, ...]
    status: str
    reason: str


class OtaUpdateManager:
    def start_rollout(self, devices: list[Device], target_version: str) -> Rollout:
        if not devices:
            raise ValueError("Cannot roll out firmware to an empty fleet")
        canary_count = max(1, (len(devices) * 5 + 99) // 100)
        canary = tuple(device.device_id for device in devices[:canary_count])
        return Rollout(target_version, canary, "canary", "Canary phase required before full rollout")

    def evaluate_canary(self, rollout: Rollout, devices: list[Device]) -> Rollout:
        canary_set = set(rollout.canary_ids)
        unhealthy = [device.device_id for device in devices if device.device_id in canary_set and not device.healthy]
        if unhealthy:
            return Rollout(rollout.target_version, rollout.canary_ids, "rolled_back", f"Canary failed health check: {', '.join(unhealthy)}")
        return Rollout(rollout.target_version, rollout.canary_ids, "approved", "Canary healthy; full rollout may proceed")
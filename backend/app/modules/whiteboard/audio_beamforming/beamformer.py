from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, sqrt


@dataclass(frozen=True)
class DirectionEstimate:
    angle_degrees: float
    confidence: float


def estimate_direction_of_arrival(samples: list[list[float]], microphone_spacing_m: float = 0.04) -> DirectionEstimate:
    if not samples or any(not channel for channel in samples):
        raise ValueError("Microphone samples cannot be empty")
    if microphone_spacing_m <= 0:
        raise ValueError("Microphone spacing must be positive")
    energies = [sum(value * value for value in channel) for channel in samples]
    strongest = max(range(len(energies)), key=energies.__getitem__)
    total = sum(energies)
    confidence = energies[strongest] / total if total else 0.0
    angle = degrees(atan2(strongest - (len(samples) - 1) / 2, max(len(samples), 1)))
    return DirectionEstimate(angle, min(1.0, confidence))


def apply_beamforming(samples: list[list[float]], delays: list[int]) -> list[float]:
    if len(samples) != len(delays) or not samples:
        raise ValueError("Each microphone channel needs one delay")
    output_length = max(len(channel) - delay for channel, delay in zip(samples, delays))
    if output_length <= 0 or any(delay < 0 for delay in delays):
        raise ValueError("Invalid delay configuration")
    return [
        sum(channel[index + delay] for channel, delay in zip(samples, delays)) / len(samples)
        for index in range(output_length)
    ]


def signal_to_noise_ratio(signal: list[float], noise: list[float]) -> float:
    if len(signal) != len(noise) or not signal:
        raise ValueError("Signal and noise must have equal non-zero length")
    signal_power = sum(value * value for value in signal) / len(signal)
    noise_power = sum(value * value for value in noise) / len(noise)
    if noise_power == 0:
        return float("inf")
    from math import log10

    return 10 * log10(signal_power / noise_power)
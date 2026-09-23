from __future__ import annotations

from dataclasses import dataclass
from random import Random


@dataclass(frozen=True)
class AugmentedStroke:
    points: tuple[tuple[float, float, float], ...]
    simulate_motor_tremor: bool


def augment_stroke(
    points: tuple[tuple[float, float, float], ...], *, count: int = 5, seed: int = 7
) -> list[AugmentedStroke]:
    if count < 5:
        raise ValueError("At least five synthetic variants are required")
    random = Random(seed)
    variants = []
    for index in range(count):
        tremor = index == 0
        variants.append(
            AugmentedStroke(
                tuple(
                    (x + random.uniform(-0.02, 0.02), y + random.uniform(-0.02, 0.02), pressure)
                    for x, y, pressure in points
                ),
                tremor,
            )
        )
    return variants

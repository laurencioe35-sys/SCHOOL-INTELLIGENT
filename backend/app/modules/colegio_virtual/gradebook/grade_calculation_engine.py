from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class WeightedCategory:
    name: str
    weight_percent: Decimal


@dataclass(frozen=True)
class GradeEntry:
    category: str
    score: Decimal | None
    max_score: Decimal


class InvalidWeightConfigurationError(Exception):
    pass


def validate_weights(categories: list[WeightedCategory]) -> None:
    total = sum(category.weight_percent for category in categories)
    if total != Decimal("100"):
        raise InvalidWeightConfigurationError(f"Las categorías suman {total}%, deben sumar exactamente 100%")


def calculate_weighted_average(
    categories: list[WeightedCategory],
    entries: list[GradeEntry],
    *,
    missing_counts_as_zero: bool,
) -> Decimal:
    validate_weights(categories)
    total = Decimal("0")
    for category in categories:
        scores: list[Decimal] = []
        for entry in entries:
            if entry.category != category.name:
                continue
            if entry.score is None:
                if missing_counts_as_zero:
                    scores.append(Decimal("0"))
                continue
            if entry.max_score <= 0:
                raise ValueError("max_score must be positive")
            scores.append((entry.score / entry.max_score) * Decimal("100"))
        if scores:
            total += (sum(scores) / len(scores)) * (category.weight_percent / Decimal("100"))
    return total.quantize(Decimal("0.01"))
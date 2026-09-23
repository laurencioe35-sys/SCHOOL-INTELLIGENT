from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reason: str
    requires_human_review: bool


def check_age_eligibility(
    birth_date: date,
    grade_min_age_years: int,
    cutoff_date: date,
    *,
    tolerance_days: int = 30,
) -> EligibilityResult:
    minimum_birth_date = cutoff_date.replace(year=cutoff_date.year - grade_min_age_years)
    age_at_cutoff_days = (minimum_birth_date - birth_date).days

    if age_at_cutoff_days >= 0:
        return EligibilityResult(True, "Cumple edad mínima al corte", False)

    if abs(age_at_cutoff_days) <= tolerance_days:
        return EligibilityResult(
            False,
            f"No cumple edad mínima por {abs(age_at_cutoff_days)} días — dentro del margen de revisión",
            True,
        )

    return EligibilityResult(
        False,
        f"No cumple edad mínima por {abs(age_at_cutoff_days)} días — fuera del margen de revisión",
        False,
    )
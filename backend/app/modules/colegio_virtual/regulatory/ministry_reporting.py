from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Callable


@dataclass(frozen=True)
class RegulatoryReportData:
    enrolled_students: int
    graduated_students: int
    average_attendance_rate: float
    grade_distribution: dict[str, int]


class MinistryReportFormatter:
    """Development formatter only; not approved for official submission."""

    is_development_only = True

    def format_for_review(self, data: RegulatoryReportData) -> bytes:
        return json.dumps(asdict(data), sort_keys=True).encode("utf-8")


def aggregate_regulatory_report_data(
    *,
    count_enrolled_students: Callable[[], int],
    count_graduated_students: Callable[[], int],
    average_attendance_rate: Callable[[], float],
    grade_distribution: Callable[[], dict[str, int]],
) -> RegulatoryReportData:
    return RegulatoryReportData(
        enrolled_students=count_enrolled_students(),
        graduated_students=count_graduated_students(),
        average_attendance_rate=average_attendance_rate(),
        grade_distribution=grade_distribution(),
    )


def generate_report_for_review(
    data: RegulatoryReportData, formatter: MinistryReportFormatter | None = None
) -> bytes:
    active_formatter = formatter or MinistryReportFormatter()
    return active_formatter.format_for_review(data)
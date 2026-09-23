import json

from app.modules.colegio_virtual.regulatory.ministry_reporting import (
    MinistryReportFormatter,
    aggregate_regulatory_report_data,
    generate_report_for_review,
)


def test_regulatory_aggregation_uses_owner_module_callbacks():
    calls: list[str] = []
    data = aggregate_regulatory_report_data(
        count_enrolled_students=lambda: calls.append("admissions") or 10,
        count_graduated_students=lambda: calls.append("credentials") or 3,
        average_attendance_rate=lambda: calls.append("virtual_classroom") or 0.92,
        grade_distribution=lambda: calls.append("gradebook") or {"A": 4, "B": 6},
    )

    assert data.enrolled_students == 10
    assert calls == ["admissions", "credentials", "virtual_classroom", "gradebook"]


def test_formatter_is_development_only_and_does_not_submit():
    data = aggregate_regulatory_report_data(
        count_enrolled_students=lambda: 1,
        count_graduated_students=lambda: 0,
        average_attendance_rate=lambda: 1.0,
        grade_distribution=lambda: {"A": 1},
    )
    formatter = MinistryReportFormatter()

    payload = generate_report_for_review(data, formatter)

    assert formatter.is_development_only is True
    assert json.loads(payload) == {
        "average_attendance_rate": 1.0,
        "enrolled_students": 1,
        "grade_distribution": {"A": 1},
        "graduated_students": 0,
    }
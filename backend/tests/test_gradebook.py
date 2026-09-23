from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.colegio_virtual.gradebook.assignment_service import AssignmentService
from app.modules.colegio_virtual.gradebook.grade_calculation_engine import (
    GradeEntry,
    InvalidWeightConfigurationError,
    WeightedCategory,
    calculate_weighted_average,
    validate_weights,
)
from app.modules.colegio_virtual.gradebook.report_card_renderer import render_report_card_pdf
from app.modules.colegio_virtual.gradebook.report_card_signature import (
    UnauthorizedSignerError,
    sign_report_card,
)


def test_rejects_weights_that_do_not_sum_to_100():
    with pytest.raises(InvalidWeightConfigurationError):
        validate_weights([WeightedCategory("tareas", Decimal("30")), WeightedCategory("examenes", Decimal("50"))])


def test_missing_grade_policy_is_explicit():
    categories = [WeightedCategory("tareas", Decimal("100"))]
    missing = [GradeEntry("tareas", None, Decimal("100"))]
    assert calculate_weighted_average(categories, missing, missing_counts_as_zero=True) == Decimal("0.00")
    assert calculate_weighted_average(categories, missing, missing_counts_as_zero=False) == Decimal("0.00")


def test_assignment_service_produces_grade_entries_for_weighted_average():
    service = AssignmentService()
    assignment = service.create_assignment(
        course_id=uuid4(), title="Quiz 1", category="tareas", max_score=Decimal("10")
    )
    entry = service.grade_assignment(assignment.id, Decimal("8"))

    assert entry.category == "tareas"
    assert calculate_weighted_average(
        [WeightedCategory("tareas", Decimal("100"))], service.grade_entries(), missing_counts_as_zero=False
    ) == Decimal("80.00")


@pytest.mark.asyncio
async def test_task_grade_report_card_render_and_authorized_signature(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    student_id, course_id = str(uuid4()), str(uuid4())
    pdf_path = await render_report_card_pdf(
        student_id=student_id, course_id=course_id, final_grade=Decimal("80.00"), version=1
    )
    with pytest.raises(UnauthorizedSignerError):
        await sign_report_card(
            None,
            tenant_id="tenant-1",
            pdf_path=pdf_path,
            signer_user_id="system",
            signer_role="system",
            webauthn_assertion={"verified": True},
        )
    signed = await sign_report_card(
        None,
        tenant_id="tenant-1",
        pdf_path=pdf_path,
        signer_user_id="coordinator-1",
        signer_role="academic_coordinator",
        webauthn_assertion={"verified": True},
    )
    assert signed.document_hash
    assert signed.signed_by == "coordinator-1"
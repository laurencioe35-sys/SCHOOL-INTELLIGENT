from __future__ import annotations

from decimal import Decimal

from .pdf_template import build_report_card_layout


async def render_report_card_pdf(*, student_id: str, course_id: str, final_grade: Decimal, version: int) -> str:
    output_path = f"artifacts/report_cards/{student_id}_{course_id}_v{version}.pdf"
    layout = build_report_card_layout(
        student_id=student_id, course_id=course_id, final_grade=final_grade, version=version
    )
    await layout.render_to_file(output_path)
    return output_path
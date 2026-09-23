from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class ReportCardLayout:
    student_id: str
    course_id: str
    final_grade: Decimal
    version: int

    async def render_to_file(self, output_path: str) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            f"REPORT_CARD\nstudent={self.student_id}\ncourse={self.course_id}\n"
            f"grade={self.final_grade}\nversion={self.version}\n"
        ).encode("utf-8")
        path.write_bytes(content)


def build_report_card_layout(*, student_id: str, course_id: str, final_grade: Decimal, version: int) -> ReportCardLayout:
    return ReportCardLayout(student_id, course_id, final_grade, version)
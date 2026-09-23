from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from .proctoring_disclosure import ProctoringConsent, verify_consent


@dataclass(frozen=True)
class ExamSession:
    id: str
    student_id: str
    active_signals: tuple[str, ...]


def start_exam_session(student_id: str, consent: ProctoringConsent | None) -> ExamSession:
    requested_signals = ("tab_switch", "response_timing", "long_paste")
    for signal in requested_signals:
        verify_consent(consent, signal)
    return ExamSession(uuid4().hex, student_id, requested_signals)
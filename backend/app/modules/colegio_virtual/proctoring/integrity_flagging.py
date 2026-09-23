from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrityFlag:
    student_id: str
    pattern: str
    confidence: float
    evidence: dict[str, object]
    notified_role: str
    sanction_applied: bool = False


def flag_interaction_pattern(
    *, student_id: str, pattern: str, confidence: float, evidence: dict[str, object]
) -> IntegrityFlag:
    if not 0 <= confidence <= 1:
        raise ValueError("Confidence must be between 0 and 1")
    if not evidence:
        raise ValueError("Integrity flags require traceable evidence")
    allowed_patterns = {"tab_switch", "response_timing", "long_paste"}
    if pattern not in allowed_patterns:
        raise ValueError("Unsupported or biometric integrity pattern")
    return IntegrityFlag(student_id, pattern, confidence, dict(evidence), "academic_coordinator")
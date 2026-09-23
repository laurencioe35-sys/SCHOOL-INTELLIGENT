from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable


class Stage(StrEnum):
    DISCOVER = "DISCOVER"
    PLAN = "PLAN"
    IMPLEMENT = "IMPLEMENT"
    TEST = "TEST"
    REVIEW = "REVIEW"
    REPAIR = "REPAIR"
    VERIFY = "VERIFY"


@dataclass
class Execution:
    task_id: str
    stage: Stage = Stage.DISCOVER
    attempts: int = 0
    evidence: list[str] = field(default_factory=list)
    status: str = "pending"
    notes: list[str] = field(default_factory=list)


class Orchestrator:
    """Motor de construcción con control de etapas y trazabilidad."""

    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts
        self._ordered_stages = [
            Stage.DISCOVER,
            Stage.PLAN,
            Stage.IMPLEMENT,
            Stage.TEST,
            Stage.REVIEW,
            Stage.VERIFY,
        ]

    def run(self, execution: Execution, checks: dict[Stage, Callable[[], bool]]) -> Execution:
        while True:
            for stage in self._ordered_stages:
                execution.stage = stage
                ok = checks.get(stage, lambda: True)()
                result = f"{stage}: {'PASS' if ok else 'FAIL'}"
                execution.evidence.append(result)
                if not ok:
                    execution.attempts += 1
                    execution.stage = Stage.REPAIR
                    execution.status = "repair"
                    execution.notes.append(f"Fallo en {stage}; reintento {execution.attempts}/{self.max_attempts}.")
                    if execution.attempts >= self.max_attempts:
                        raise RuntimeError(f"Execution stopped after {self.max_attempts} failed attempts")
                    break
            else:
                execution.status = "done"
                execution.stage = Stage.VERIFY
                return execution

    def enqueue(self, task_id: str, checks: dict[Stage, Callable[[], bool]]) -> Execution:
        execution = Execution(task_id=task_id)
        return self.run(execution, checks)

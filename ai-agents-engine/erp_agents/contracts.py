from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class BuildStage(StrEnum):
    DISCOVER = "DISCOVER"
    PLAN = "PLAN"
    IMPLEMENT = "IMPLEMENT"
    TEST = "TEST"
    REVIEW = "REVIEW"
    REPAIR = "REPAIR"
    VERIFY = "VERIFY"


@dataclass(frozen=True)
class BuildTask:
    task_id: str
    title: str
    module: str
    depends_on: tuple[str, ...] = ()
    required_roles: tuple[str, ...] = ()
    validation_command: str | None = None
    execute_validation: bool = False
    max_repairs: int = 2
    implementation_spec: str | None = None
    target_files: tuple[str, ...] = ()
    requires_code_generation: bool = False
    blocked_reason: str | None = None


@dataclass
class BuildContext:
    workspace: str
    evidence: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    repair_tasks: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentReport:
    role: str
    task_id: str
    stage: BuildStage
    ok: bool
    message: str

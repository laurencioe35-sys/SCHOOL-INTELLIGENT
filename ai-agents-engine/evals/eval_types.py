from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class EvalCase:
    id: str
    agent: str
    input: dict[str, Any]
    checks: list[Callable[[Any], CheckResult]] = field(default_factory=list)


@dataclass
class CaseResult:
    case_id: str
    agent: str
    passed: bool
    score: float
    check_results: list[CheckResult]
    error: str | None = None

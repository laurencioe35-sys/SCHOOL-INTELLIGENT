from __future__ import annotations

import argparse
import json
import os
import time
from enum import StrEnum
from pathlib import Path

from erp_agents.runner import BuildRunner
from run_build_loop import load_tasks
from erp_agents.contracts import BuildContext


class OrchestratorMode(StrEnum):
    BUILDING = "BUILDING"
    MAINTAINING = "MAINTAINING"


def _gemini_configured(workspace: Path) -> bool:
    if os.getenv("GEMINI_API_KEY"):
        return True
    env_path = workspace / ".env"
    if not env_path.exists():
        return False
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("GEMINI_API_KEY="):
            return bool(line.split("=", 1)[1].strip())
    return False


def write_checkpoint(path: Path, mode: OrchestratorMode, completed: list[str], blocked: dict[str, str], evidence: list[str], reports: list[dict[str, str]]) -> None:
    path.write_text(
        json.dumps(
            {"mode": mode, "completed": completed, "blocked": blocked, "evidence": evidence, "reports": reports},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def run_cycle(root: Path, checkpoint_path: Path) -> OrchestratorMode:
    tasks = load_tasks(root / "config" / "erp_build_backlog.json")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.exists() else {}
    task_ids = {task.task_id for task in tasks}
    completed_ids = set(checkpoint.get("completed", [])) & task_ids
    context = BuildContext(workspace=str(root.parent))
    result = BuildRunner().run(tasks, context, completed_ids=completed_ids)
    completed_ids.update(result.completed)
    mode = OrchestratorMode.MAINTAINING if len(completed_ids) == len(tasks) and not result.blocked else OrchestratorMode.BUILDING
    reports = [
        {"task_id": report.task_id, "stage": str(report.stage), "role": report.role, "ok": str(report.ok), "message": report.message}
        for report in result.reports
    ]
    write_checkpoint(checkpoint_path, mode, sorted(completed_ids), result.blocked, result.evidence, reports)
    gemini_configured = _gemini_configured(root.parent)
    print(
        f"SUPERVISION mode={mode} completed={len(completed_ids)}/{len(tasks)} "
        f"blocked={len(result.blocked)} evidence={len(result.evidence)} "
        f"reports={len(result.reports)} gemini_configured={gemini_configured}",
        flush=True,
    )
    return mode


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous ERP construction and maintenance loop")
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).parent
    checkpoint_path = root / "config" / "build_checkpoint.json"

    while True:
        run_cycle(root, checkpoint_path)
        if args.once:
            return
        time.sleep(max(15, args.interval))


if __name__ == "__main__":
    main()
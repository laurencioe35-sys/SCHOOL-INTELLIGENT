from __future__ import annotations

import json
from pathlib import Path

from erp_agents.contracts import BuildContext, BuildTask
from erp_agents.runner import BuildRunner


def load_tasks(path: Path) -> list[BuildTask]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        BuildTask(
            task_id=item["task_id"],
            title=item["title"],
            module=item["module"],
            depends_on=tuple(item.get("depends_on", [])),
            required_roles=tuple(item.get("required_roles", [])),
            validation_command=item.get("validation_command"),
            execute_validation=item.get("execute_validation", False),
            max_repairs=item.get("max_repairs", 2),
            implementation_spec=item.get("implementation_spec"),
            target_files=tuple(item.get("target_files", [])),
            requires_code_generation=item.get("requires_code_generation", False),
            blocked_reason=item.get("blocked_reason"),
        )
        for item in payload["tasks"]
    ]


def main() -> None:
    root = Path(__file__).parent
    tasks = load_tasks(root / "config" / "erp_build_backlog.json")
    result = BuildRunner().run(tasks, BuildContext(workspace=str(root.parent)))
    for report in result.reports:
        print(f"[{report.stage}] [{report.role}] {report.task_id}: {report.message}")
    print(f"COMPLETED: {', '.join(result.completed)}")


if __name__ == "__main__":
    main()
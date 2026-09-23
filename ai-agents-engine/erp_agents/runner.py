from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import AgentReport, BuildContext, BuildStage, BuildTask
from .registry import BuildAgentRegistry


@dataclass
class BuildRun:
    completed: list[str] = field(default_factory=list)
    blocked: dict[str, str] = field(default_factory=dict)
    reports: list[AgentReport] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


class BuildRunner:
    def __init__(self, registry: BuildAgentRegistry | None = None) -> None:
        self.registry = registry or BuildAgentRegistry()

    def run(self, tasks: list[BuildTask], context: BuildContext, completed_ids: set[str] | None = None) -> BuildRun:
        self._validate_backlog(tasks)
        registered_roles = set(self.registry._agents)
        for task in tasks:
            missing_roles = sorted(set(task.required_roles) - registered_roles)
            if missing_roles:
                raise RuntimeError(f"Build task {task.task_id} requires unregistered roles: {missing_roles}")
        result = BuildRun(completed=sorted(completed_ids or set()))
        pending = {task.task_id: task for task in tasks if task.task_id not in result.completed}
        while pending:
            ready = [task for task in pending.values() if all(dep in result.completed for dep in task.depends_on)]
            if not ready:
                for task in pending.values():
                    dependencies = ", ".join(task.depends_on) or "unknown scheduler condition"
                    result.blocked[task.task_id] = f"unresolved dependency state: {dependencies}"
                break
            for task in ready:
                if task.blocked_reason:
                    result.blocked[task.task_id] = task.blocked_reason
                    del pending[task.task_id]
                    continue
                repairs = 0
                stages = [stage for stage in BuildStage if stage != BuildStage.REPAIR]
                stage_index = 0
                while stage_index < len(stages):
                    stage = stages[stage_index]
                    reports = self.registry.run(task, stage, context)
                    result.reports.extend(reports)
                    failed = [report for report in reports if not report.ok]
                    if failed and stage != BuildStage.REPAIR:
                        repairs += 1
                        if repairs > task.max_repairs:
                            if any("Agent role is not registered" in report.message for report in failed):
                                raise RuntimeError(f"Build agent failed task {task.task_id} at {stage}")
                            result.blocked[task.task_id] = f"failed at {stage}: {failed[-1].message}"
                            del pending[task.task_id]
                            stage_index = len(stages)
                            break
                        context.history.append(f"{task.task_id}: repair {repairs} after {stage}")
                        repair_reports = self.registry.run(task, BuildStage.REPAIR, context)
                        result.reports.extend(repair_reports)
                        if any(not report.ok for report in repair_reports):
                            result.blocked[task.task_id] = f"repair failed at {stage}"
                            del pending[task.task_id]
                            stage_index = len(stages)
                            break
                        context.findings.clear()
                        stage_index = 0
                        continue
                    stage_index += 1
                if task.task_id not in result.blocked:
                    result.completed.append(task.task_id)
                    result.evidence.append(f"{task.task_id}: all stages completed with executable validation")
                    del pending[task.task_id]
        return result

    @staticmethod
    def _validate_backlog(tasks: list[BuildTask]) -> None:
        task_ids = [task.task_id for task in tasks]
        duplicates = sorted({task_id for task_id in task_ids if task_ids.count(task_id) > 1})
        if duplicates:
            raise ValueError(f"Build backlog contains duplicate task IDs: {duplicates}")
        known_ids = set(task_ids)
        for task in tasks:
            missing = sorted(set(task.depends_on) - known_ids)
            if missing:
                raise ValueError(f"Task {task.task_id} depends on unknown tasks: {missing}")
        visiting: set[str] = set()
        visited: set[str] = set()
        by_id = {task.task_id: task for task in tasks}

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError(f"Build backlog contains a dependency cycle at {task_id}")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in by_id[task_id].depends_on:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in task_ids:
            visit(task_id)
        for task in tasks:
            if task.requires_code_generation:
                if "code_writer" not in task.required_roles:
                    raise ValueError(f"Task {task.task_id} requires the code_writer role")
                if not task.implementation_spec:
                    raise ValueError(f"Task {task.task_id} requires implementation_spec")
                if not task.target_files:
                    raise ValueError(f"Task {task.task_id} requires target_files")
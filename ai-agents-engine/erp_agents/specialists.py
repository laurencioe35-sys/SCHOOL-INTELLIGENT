from __future__ import annotations

import subprocess
from pathlib import Path

from .contracts import AgentReport, BuildContext, BuildStage, BuildTask


class BuildAgent:
    role: str

    def report(self, task: BuildTask, stage: BuildStage, message: str, ok: bool = True) -> AgentReport:
        return AgentReport(self.role, task.task_id, stage, ok, message)

    def run(self, task: BuildTask, stage: BuildStage, context: BuildContext) -> AgentReport:
        raise NotImplementedError


class DiscoveryAgent(BuildAgent):
    role = "discovery"

    def run(self, task: BuildTask, stage: BuildStage, context: BuildContext) -> AgentReport:
        context.evidence.append(f"{task.task_id}: module={task.module}; dependencies={task.depends_on}")
        if stage == BuildStage.DISCOVER and Path(context.workspace).exists():
            module_path = Path(context.workspace) / task.module
            if not module_path.exists():
                finding = f"{task.task_id}: documented module is missing: {task.module}"
                context.findings.append(finding)
                return self.report(task, stage, finding, ok=False)
        return self.report(task, stage, f"Inspected scope for {task.module}")


class PlanningAgent(BuildAgent):
    role = "planning"

    def run(self, task: BuildTask, stage: BuildStage, context: BuildContext) -> AgentReport:
        context.artifacts.append(f"plan:{task.task_id}")
        return self.report(task, stage, f"Planned implementation for {task.title}")


class BackendAgent(BuildAgent):
    role = "backend"

    def run(self, task: BuildTask, stage: BuildStage, context: BuildContext) -> AgentReport:
        artifact = Path(context.workspace) / task.module
        if stage == BuildStage.IMPLEMENT and not artifact.exists():
            finding = f"{task.task_id}: backend artifact missing at IMPLEMENT: {task.module}"
            context.findings.append(finding)
            return self.report(task, stage, finding, ok=False)
        context.artifacts.append(f"backend:{task.module}")
        return self.report(task, stage, f"Backend artifact verified: {task.module}")


class FrontendAgent(BuildAgent):
    role = "frontend"

    def run(self, task: BuildTask, stage: BuildStage, context: BuildContext) -> AgentReport:
        artifact = Path(context.workspace) / task.module
        if stage == BuildStage.IMPLEMENT and not artifact.exists():
            finding = f"{task.task_id}: frontend artifact missing at IMPLEMENT: {task.module}"
            context.findings.append(finding)
            return self.report(task, stage, finding, ok=False)
        context.artifacts.append(f"frontend:{task.module}")
        return self.report(task, stage, f"Frontend artifact verified: {task.module}")


class QualityAgent(BuildAgent):
    role = "quality"

    def run(self, task: BuildTask, stage: BuildStage, context: BuildContext) -> AgentReport:
        if stage != BuildStage.TEST:
            return self.report(task, stage, "Quality agent idle outside TEST")
        if stage == BuildStage.TEST and not task.validation_command:
            return self.report(task, stage, "Task has no executable validation command", ok=False)
        if stage == BuildStage.TEST and task.execute_validation:
            completed = subprocess.run(
                task.validation_command,
                cwd=context.workspace,
                shell=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if completed.returncode != 0:
                finding = f"{task.task_id}: validation failed ({completed.returncode}): {completed.stdout[-400:]}{completed.stderr[-400:]}"
                context.findings.append(finding)
                return self.report(task, stage, finding, ok=False)
            context.evidence.append(f"{task.task_id}: validation passed")
        return self.report(task, stage, task.validation_command or "Validation evidence required")


class SecurityAgent(BuildAgent):
    role = "security"

    def run(self, task: BuildTask, stage: BuildStage, context: BuildContext) -> AgentReport:
        if stage not in (BuildStage.DISCOVER, BuildStage.REVIEW, BuildStage.VERIFY):
            return self.report(task, stage, "Security agent idle for this stage")
        context.evidence.append(f"{task.task_id}: tenant and audit review required")
        return self.report(task, stage, f"Security review required for {task.module}")


class ReviewAgent(BuildAgent):
    role = "review"

    def run(self, task: BuildTask, stage: BuildStage, context: BuildContext) -> AgentReport:
        if stage != BuildStage.REVIEW:
            return self.report(task, stage, "Review agent idle outside REVIEW")
        if stage == BuildStage.REVIEW and context.findings:
            return self.report(task, stage, f"Review found {len(context.findings)} finding(s)", ok=False)
        return self.report(task, stage, "Review passed with available evidence")


class RepairAgent(BuildAgent):
    role = "repair"

    def run(self, task: BuildTask, stage: BuildStage, context: BuildContext) -> AgentReport:
        if stage != BuildStage.REPAIR:
            return self.report(task, stage, "Repair agent idle outside REPAIR")
        repair_id = f"repair:{task.task_id}:{len(context.repair_tasks) + 1}"
        context.repair_tasks.append(repair_id)
        context.artifacts.append(repair_id)
        return self.report(task, stage, f"Created repair task {repair_id}")


class VerificationAgent(BuildAgent):
    role = "verify"

    def run(self, task: BuildTask, stage: BuildStage, context: BuildContext) -> AgentReport:
        if stage != BuildStage.VERIFY:
            return self.report(task, stage, "Verification agent idle outside VERIFY")
        if stage == BuildStage.VERIFY and context.findings:
            return self.report(task, stage, "Verification blocked by unresolved findings", ok=False)
        return self.report(task, stage, "Verified task evidence and artifacts")

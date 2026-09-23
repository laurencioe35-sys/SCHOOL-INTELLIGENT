from __future__ import annotations

from .contracts import AgentReport, BuildContext, BuildStage, BuildTask
from .code_writer import GeminiCodeWriterAgent
from .specialists import (
    BackendAgent,
    BuildAgent,
    DiscoveryAgent,
    FrontendAgent,
    PlanningAgent,
    QualityAgent,
    RepairAgent,
    ReviewAgent,
    SecurityAgent,
    VerificationAgent,
)


class BuildAgentRegistry:
    def __init__(self, agents: list[BuildAgent] | None = None) -> None:
        self._agents = {agent.role: agent for agent in (agents or self.default_agents())}

    @staticmethod
    def default_agents() -> list[BuildAgent]:
        return [
            DiscoveryAgent(),
            PlanningAgent(),
            GeminiCodeWriterAgent(),
            BackendAgent(),
            FrontendAgent(),
            QualityAgent(),
            SecurityAgent(),
            ReviewAgent(),
            RepairAgent(),
            VerificationAgent(),
        ]

    def run(self, task: BuildTask, stage: BuildStage, context: BuildContext) -> list[AgentReport]:
        reports = []
        for role in task.required_roles:
            agent = self._agents.get(role)
            if agent is None:
                reports.append(AgentReport(role, task.task_id, stage, False, "Agent role is not registered"))
                continue
            reports.append(agent.run(task, stage, context))
        return reports
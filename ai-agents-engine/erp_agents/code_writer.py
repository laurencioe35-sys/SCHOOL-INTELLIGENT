from __future__ import annotations

import json
import os
from pathlib import Path

from config.llm_client import call_llm, require_real_provider

from .contracts import AgentReport, BuildContext, BuildStage, BuildTask
from .specialists import BuildAgent


class GeminiCodeWriterAgent(BuildAgent):
    role = "code_writer"

    def run(self, task: BuildTask, stage: BuildStage, context: BuildContext) -> AgentReport:
        if stage != BuildStage.IMPLEMENT:
            return self.report(task, stage, "Code writer idle outside IMPLEMENT")
        if not task.requires_code_generation:
            return self.report(task, stage, "Task is maintenance-only; no code generation requested")
        if not task.implementation_spec or not task.target_files:
            finding = f"{task.task_id}: implementation_spec and target_files are required"
            context.findings.append(finding)
            return self.report(task, stage, finding, ok=False)

        try:
            require_real_provider()
            response = call_llm(
                "You are a senior software engineer. Return only valid JSON with a files array. "
                "Each item must contain path and content. Modify only the requested target files. "
                "Do not return markdown fences, explanations, secrets, or placeholders.",
                json.dumps({
                    "task_id": task.task_id,
                    "title": task.title,
                    "specification": task.implementation_spec,
                    "target_files": task.target_files,
                }, ensure_ascii=False),
            )
            payload = json.loads(response)
            files = payload.get("files")
            if not isinstance(files, list):
                raise ValueError("Gemini response must contain a files array")
            allowed = {Path(path).as_posix() for path in task.target_files}
            written: list[str] = []
            for item in files:
                relative = Path(str(item.get("path", ""))).as_posix()
                if relative not in allowed or relative.startswith("../") or ":" in relative:
                    raise ValueError(f"Generated path is outside target_files: {relative}")
                content = item.get("content")
                if not isinstance(content, str) or not content.strip():
                    raise ValueError(f"Generated content is empty: {relative}")
                destination = Path(context.workspace) / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(destination.suffix + ".agent.tmp")
                temporary.write_text(content, encoding="utf-8")
                temporary.replace(destination)
                written.append(relative)
            if set(written) != allowed:
                raise ValueError("Gemini did not return every target file")
        except Exception as error:
            finding = f"{task.task_id}: code generation failed: {error}"
            context.findings.append(finding)
            return self.report(task, stage, finding, ok=False)

        context.artifacts.extend(f"generated:{path}" for path in written)
        return self.report(task, stage, f"Gemini wrote and committed {len(written)} target file(s)")

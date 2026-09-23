import json

from erp_agents.code_writer import GeminiCodeWriterAgent
from erp_agents.contracts import BuildContext, BuildStage, BuildTask


def test_code_writer_writes_only_declared_targets(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "configured-for-test")
    monkeypatch.setattr(
        "erp_agents.code_writer.call_llm",
        lambda *_args, **_kwargs: json.dumps({"files": [{"path": "generated/module.py", "content": "VALUE = 42\n"}]}),
    )
    task = BuildTask(
        "writer-task",
        "Generate module",
        "generated/module.py",
        required_roles=("code_writer",),
        implementation_spec="Create a module exposing VALUE=42.",
        target_files=("generated/module.py",),
        requires_code_generation=True,
    )

    report = GeminiCodeWriterAgent().run(task, BuildStage.IMPLEMENT, BuildContext(workspace=str(tmp_path)))

    assert report.ok
    assert (tmp_path / "generated/module.py").read_text(encoding="utf-8") == "VALUE = 42\n"


def test_code_writer_rejects_missing_contract(tmp_path):
    task = BuildTask("writer-task", "Generate module", "generated/module.py", requires_code_generation=True)

    report = GeminiCodeWriterAgent().run(task, BuildStage.IMPLEMENT, BuildContext(workspace=str(tmp_path)))

    assert not report.ok
    assert "implementation_spec" in report.message

from erp_agents.contracts import BuildContext, BuildStage, BuildTask
from erp_agents.registry import BuildAgentRegistry
from erp_agents.runner import BuildRunner


def test_build_runner_respects_dependencies_and_runs_all_stages():
    tasks = [
        BuildTask("second", "Second", "second", ("first",), ("discovery", "quality"), "pytest second"),
        BuildTask("first", "First", "first", (), ("discovery", "quality"), "pytest first"),
    ]
    context = BuildContext(workspace="workspace")

    result = BuildRunner(BuildAgentRegistry()).run(tasks, context)

    assert result.completed == ["first", "second"]
    assert len(result.reports) == 2 * (len(BuildStage) - 1) * 2


def test_missing_agent_role_is_a_failure():
    task = BuildTask("task", "Task", "module", required_roles=("unknown",))

    try:
        BuildRunner().run([task], BuildContext(workspace="workspace"))
    except RuntimeError as error:
        assert "task" in str(error)
    else:
        raise AssertionError("unregistered role must fail the build")


def test_runner_exposes_repair_and_verification_roles():
    roles = {agent.role for agent in BuildAgentRegistry.default_agents()}

    assert {"review", "repair", "verify"}.issubset(roles)


def test_implementation_agents_report_existing_artifacts():
    task = BuildTask("backend-task", "Backend", "ai-agents-engine", required_roles=("backend",))
    result = BuildRunner().run([task], BuildContext(workspace=".."))

    implementation_reports = [report for report in result.reports if report.stage == BuildStage.IMPLEMENT]
    assert implementation_reports[0].ok is True
    assert "artifact verified" in implementation_reports[0].message


def test_backlog_rejects_unknown_dependency():
    task = BuildTask("task", "Task", "ai-agents-engine", ("missing",))

    try:
        BuildRunner().run([task], BuildContext(workspace=".."))
    except ValueError as error:
        assert "unknown tasks" in str(error)
    else:
        raise AssertionError("unknown dependencies must fail before execution")


def test_backlog_rejects_cycles():
    tasks = [
        BuildTask("a", "A", "ai-agents-engine", ("b",)),
        BuildTask("b", "B", "ai-agents-engine", ("a",)),
    ]

    try:
        BuildRunner().run(tasks, BuildContext(workspace=".."))
    except ValueError as error:
        assert "cycle" in str(error)
    else:
        raise AssertionError("dependency cycles must fail before execution")


def test_code_generation_requires_explicit_writer_contract():
    task = BuildTask("generated", "Generated", "module.py", requires_code_generation=True)

    try:
        BuildRunner().run([task], BuildContext(workspace=".."))
    except ValueError as error:
        assert "code_writer" in str(error)
    else:
        raise AssertionError("code generation without a writer contract must fail")
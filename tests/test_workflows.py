from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _workflow_path(name: str) -> Path:
    return _repo_root().joinpath(".github", "workflows", name)


def _load_workflow(name: str) -> dict:
    path = _workflow_path(name)
    assert path.exists(), f"Missing workflow file: {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _job_steps(workflow: dict, job_name: str) -> list[dict]:
    jobs = workflow.get("jobs", {})
    assert job_name in jobs, f"Missing job: {job_name}"
    steps = jobs[job_name].get("steps", [])
    assert isinstance(steps, list)
    return steps


def _find_step_index(steps: list[dict], name_fragment: str) -> int:
    lowered = name_fragment.lower()
    for index, step in enumerate(steps):
        if lowered in str(step.get("name", "")).lower():
            return index
    raise AssertionError(f"Step containing '{name_fragment}' was not found")


def _all_run_commands(workflow: dict) -> list[str]:
    commands: list[str] = []
    jobs = workflow.get("jobs", {})
    for job in jobs.values():
        for step in job.get("steps", []):
            run = step.get("run")
            if isinstance(run, str):
                commands.append(run)
    return commands


def test_ci_workflow_contract() -> None:
    workflow = _load_workflow("ci.yml")

    triggers = workflow.get("on", {})
    assert "push" in triggers
    assert "pull_request" in triggers

    steps = _job_steps(workflow, "build")
    defaults = workflow.get("jobs", {}).get("build", {}).get("defaults", {})
    assert defaults.get("run", {}).get("shell") == "bash"

    uses = [str(step.get("uses", "")) for step in steps if "uses" in step]
    assert "actions/checkout@v4" in uses
    assert "actions/setup-python@v5" in uses

    setup_python = next(step for step in steps if step.get("uses") == "actions/setup-python@v5")
    assert setup_python.get("with", {}).get("python-version") == "3.13"
    assert setup_python.get("with", {}).get("cache") == "pip"
    cache_paths = setup_python.get("with", {}).get("cache-dependency-path", "")
    assert "requirements.txt" in cache_paths
    assert "requirements-ops.txt" in cache_paths
    assert "requirements-dev.txt" in cache_paths

    run_commands = _all_run_commands(workflow)
    joined = "\n".join(run_commands)
    assert "pip install -r requirements-dev.txt" in joined
    assert "requirements-agentdev" not in joined
    assert "python -m ruff check ." in joined
    assert "python -m pytest" in joined
    assert "python -m pytest tests/test_eval_datasets.py" in joined
    assert "az bicep build" in joined


def test_deploy_workflow_contract() -> None:
    workflow = _load_workflow("deploy-evaluate.yml")

    triggers = workflow.get("on", {})
    assert triggers.get("push", {}).get("branches") == ["main"]
    assert "workflow_dispatch" in triggers

    permissions = workflow.get("permissions", {})
    assert permissions.get("contents") == "read"
    assert permissions.get("id-token") == "write"

    concurrency = workflow.get("concurrency", {})
    assert concurrency.get("cancel-in-progress") is False

    steps = _job_steps(workflow, "deploy_evaluate")
    defaults = workflow.get("jobs", {}).get("deploy_evaluate", {}).get("defaults", {})
    assert defaults.get("run", {}).get("shell") == "bash"

    uses = [str(step.get("uses", "")) for step in steps if "uses" in step]
    assert "actions/checkout@v4" in uses
    assert "actions/setup-python@v5" in uses
    assert "Azure/setup-azd@v2" in uses

    run_commands = _all_run_commands(workflow)
    joined = "\n".join(run_commands)

    assert "azd auth login --client-id" in joined
    assert "--federated-credential-provider github" in joined
    assert "--tenant-id" in joined
    assert "AZURE_CLIENT_SECRET" not in joined
    assert "azd env set AZURE_AI_PROJECT_ENDPOINT \"$FOUNDRY_PROJECT_ENDPOINT\"" in joined
    assert "azd env set FOUNDRY_PROJECT_ENDPOINT \"$FOUNDRY_PROJECT_ENDPOINT\"" in joined

    assert "azd extension install microsoft.foundry --no-prompt" in joined
    assert "azd extension add microsoft.foundry" not in joined
    assert "azd ext install microsoft.foundry" not in joined
    assert "AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd" in joined

    # Verify all azd invocations set the required user agent inline.
    for command in run_commands:
        for line in command.splitlines():
            stripped = line.strip()
            if "azd " not in stripped:
                continue
            if stripped.startswith("#"):
                continue
            assert "AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd" in stripped

    assert "python -m lifecycle_ops.provisioning.knowledge_bases" not in joined
    assert "python -m lifecycle_ops.provisioning.toolboxes" not in joined
    assert "python -m lifecycle_ops.provisioning.rbac" not in joined
    assert "python -m lifecycle_ops.provisioning.continuous_eval" not in joined

    smoke_lines = [
        line.strip()
        for command in run_commands
        for line in command.splitlines()
        if "azd ai agent invoke" in line
    ]
    assert len(smoke_lines) == 3
    assert any("development-agent" in line for line in smoke_lines)
    assert any("human-resources-agent" in line for line in smoke_lines)
    assert any("marketing-agent" in line for line in smoke_lines)
    assert all("--no-prompt" in line for line in smoke_lines)
    assert all("--output raw" in line for line in smoke_lines)
    assert (
        "python -m lifecycle_ops.operations.deployment_check "
        "--smoke-artifacts-dir artifacts"
    ) in joined

    # Stage order enforcement.
    build_index = _find_step_index(steps, "build")
    provision_index = _find_step_index(steps, "provision")
    deploy_index = _find_step_index(steps, "deploy")
    smoke_index = _find_step_index(steps, "smoke")
    evaluate_index = _find_step_index(steps, "evaluate")
    operate_index = _find_step_index(steps, "operate")
    assert build_index < provision_index < deploy_index
    assert deploy_index < smoke_index < evaluate_index < operate_index

    assert "azd ai agent eval run" in joined
    eval_gate_cmd = (
        "python -m lifecycle_ops.evaluation.gate "
        "--config evals/eval.yaml "
        "--results artifacts/eval-results.json "
        "--output artifacts/eval-gate.json"
    )
    assert eval_gate_cmd in joined
    assert "python -m lifecycle_ops.operations.agent365.readiness" in joined
    assert "python -m lifecycle_ops.operations.agent365.registry" in joined
    assert "A365_PREREQUISITES_CLAIMED" in joined
    assert (
        "python -m lifecycle_ops.operations.agent365.registry "
        "> artifacts/agent365-registry.json"
    ) in joined

    # Evaluate must happen before operate regardless of step text casing.
    assert evaluate_index < operate_index

    artifact_uses = [u for u in uses if u.startswith("actions/upload-artifact@")]
    assert "actions/upload-artifact@v4" in artifact_uses
    for step in steps:
        if step.get("uses") == "actions/upload-artifact@v4":
            assert step.get("with", {}).get("if-no-files-found") == "warn"


def test_verify_deployment_parses_azd_env_lines() -> None:
    from lifecycle_ops.operations.deployment_check import parse_azd_env_values

    parsed = parse_azd_env_values(
        'A=1\nB="two"\nC=\'three\'\nINVALID\nEMPTY=\n'
    )
    assert parsed == {
        "A": "1",
        "B": "two",
        "C": "three",
        "EMPTY": "",
    }


def test_verify_deployment_does_not_build_invoke_args() -> None:
    script_text = _repo_root().joinpath(
        "src", "lifecycle_ops", "operations", "deployment_check.py"
    ).read_text(encoding="utf-8")
    assert "agent invoke" not in script_text


def test_verify_deployment_fails_when_any_agent_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    from lifecycle_ops.operations import deployment_check as target

    call_log: list[list[str]] = []

    def fake_run(args: list[str], *, capture_json: bool = False):
        call_log.append(args)
        if args[:4] == ["azd", "env", "get-values", "--no-prompt"]:
            return "AZURE_ENV_NAME=dev\n"
        if args[:5] == ["azd", "ai", "agent", "show", "development-agent"]:
            return {"status": "active"}
        if args[:5] == ["azd", "ai", "agent", "show", "human-resources-agent"]:
            return {"status": "failed"}
        if args[:5] == ["azd", "ai", "agent", "show", "marketing-agent"]:
            return {"status": "active"}
        raise AssertionError(f"Unexpected args: {args}")

    monkeypatch.setattr(target, "run_command", fake_run)

    exit_code = target.main([
        "--smoke-artifacts-dir",
        str(_repo_root().joinpath(".pytest_cache")),
        "--output-json",
        str(_repo_root().joinpath(".pytest_cache", "verify-deployment.json")),
    ])
    assert exit_code != 0
    assert not any(args[:4] == ["azd", "ai", "agent", "invoke"] for args in call_log)


def test_verify_deployment_writes_summary_when_all_agents_active(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from lifecycle_ops.operations import deployment_check as target

    def fake_run(args: list[str], *, capture_json: bool = False):
        if args[:4] == ["azd", "env", "get-values", "--no-prompt"]:
            return "AZURE_ENV_NAME=dev\n"
        if args[:4] == ["azd", "ai", "agent", "show"]:
            return {"status": "active", "name": args[4]}
        raise AssertionError(f"Unexpected args: {args}")

    monkeypatch.setattr(target, "run_command", fake_run)

    for dept in ["development", "human-resources", "marketing"]:
        tmp_path.joinpath(f"smoke-{dept}.txt").write_text("non-empty response\n", encoding="utf-8")

    output_json = tmp_path.joinpath("verify-summary.json")
    exit_code = target.main([
        "--smoke-artifacts-dir",
        str(tmp_path),
        "--output-json",
        str(output_json),
    ])
    assert exit_code == 0

    summary = json.loads(output_json.read_text(encoding="utf-8"))
    assert summary["status"] == "success"
    assert set(summary["agents"].keys()) == {
        "development-agent",
        "human-resources-agent",
        "marketing-agent",
    }
    assert all(item["status"] == "active" for item in summary["agents"].values())
    assert all(item["smoke_response"] for item in summary["agents"].values())


def test_verify_deployment_requires_smoke_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from lifecycle_ops.operations import deployment_check as target

    def fake_run(args: list[str], *, capture_json: bool = False):
        if args[:4] == ["azd", "env", "get-values", "--no-prompt"]:
            return "AZURE_ENV_NAME=dev\n"
        if args[:4] == ["azd", "ai", "agent", "show"]:
            return {"status": "active", "name": args[4]}
        raise AssertionError(f"Unexpected args: {args}")

    monkeypatch.setattr(target, "run_command", fake_run)

    tmp_path.joinpath("smoke-development.txt").write_text("ok\n", encoding="utf-8")
    tmp_path.joinpath("smoke-human-resources.txt").write_text("\n", encoding="utf-8")
    # smoke-marketing.txt intentionally absent

    output_json = tmp_path.joinpath("verify-summary.json")
    exit_code = target.main([
        "--smoke-artifacts-dir",
        str(tmp_path),
        "--output-json",
        str(output_json),
    ])
    assert exit_code != 0

    summary = json.loads(output_json.read_text(encoding="utf-8"))
    assert summary["status"] == "failure"
    assert any("smoke-human-resources.txt" in item for item in summary["failures"])
    assert any("smoke-marketing.txt" in item for item in summary["failures"])
from __future__ import annotations

import fnmatch
from pathlib import Path

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_azure_yaml() -> dict:
    return yaml.safe_load(_repo_root().joinpath("azure.yaml").read_text(encoding="utf-8"))


def _load_agentignore_patterns() -> list[str]:
    lines = _repo_root().joinpath(".agentignore").read_text(encoding="utf-8").splitlines()
    patterns: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        patterns.append(stripped)
    return patterns


def _is_ignored(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/").strip("/")
    for pattern in patterns:
        p = pattern.replace("\\", "/")
        if p.endswith("/"):
            prefix = p.rstrip("/") + "/"
            if normalized.startswith(prefix):
                return True
        if fnmatch.fnmatch(normalized, p) or fnmatch.fnmatch("/" + normalized, p):
            return True
    return False


def test_hosted_agent_services_share_root_entrypoint() -> None:
    services = _load_azure_yaml()["services"]
    expected_departments = {
        "development-agent": "development",
        "human-resources-agent": "human-resources",
        "marketing-agent": "marketing",
    }

    for service_name, department in expected_departments.items():
        service = services[service_name]
        assert service["host"] == "azure.ai.agent"
        assert service["project"] == "."
        assert service["codeConfiguration"]["entryPoint"] == "agent.py"
        assert service["codeConfiguration"]["dependencyResolution"] == "remote_build"
        env_values = {
            item["name"]: item["value"]
            for item in service.get("environmentVariables", [])
            if isinstance(item, dict) and "name" in item and "value" in item
        }
        assert env_values["DEPARTMENT"] == department
        assert env_values["TOOLBOX_ENDPOINT"] == (
            "${TOOLBOX_ENDPOINT_" + department.replace("-", "_").upper() + "}"
        )


def test_hosted_agent_project_packaging_includes_required_runtime_assets() -> None:
    root = _repo_root()
    patterns = _load_agentignore_patterns()
    services = _load_azure_yaml()["services"]

    for service_name in ["development-agent", "human-resources-agent", "marketing-agent"]:
        service = services[service_name]
        project = service["project"]
        assert project == ".", "Hosted agent project must be repository root."

        entrypoint = service["codeConfiguration"]["entryPoint"]
        env_values = {
            item["name"]: item["value"]
            for item in service.get("environmentVariables", [])
            if isinstance(item, dict) and "name" in item and "value" in item
        }
        required_paths = [
            "requirements.txt",
            "departments.yaml",
            "src/lifecycle_agent/__init__.py",
            entrypoint,
            f"src/lifecycle_agent/prompts/{env_values['DEPARTMENT']}.md",
        ]

        for relative_path in required_paths:
            assert root.joinpath(relative_path).exists(), (
                f"Missing required runtime file: {relative_path}"
            )
            assert not _is_ignored(relative_path, patterns), (
                f"Required runtime file is ignored: {relative_path}"
            )


def test_agentignore_excludes_local_env_and_azure_state() -> None:
    patterns = _load_agentignore_patterns()
    assert _is_ignored(".env", patterns)
    assert _is_ignored(".env.local", patterns)
    assert _is_ignored(".azure/config.json", patterns)
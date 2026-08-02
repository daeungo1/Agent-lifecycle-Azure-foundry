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


def test_hosted_agent_services_use_root_project_and_nested_entrypoints() -> None:
    services = _load_azure_yaml()["services"]
    expected = {
        "development-agent": "services/agents/development/main.py",
        "human-resources-agent": "services/agents/human-resources/main.py",
        "marketing-agent": "services/agents/marketing/main.py",
    }
    expected_department = {
        "development-agent": "development",
        "human-resources-agent": "human-resources",
        "marketing-agent": "marketing",
    }

    for service_name, expected_entrypoint in expected.items():
        service = services[service_name]
        assert service["host"] == "azure.ai.agent"
        assert service["project"] == "."
        assert service["codeConfiguration"]["entryPoint"] == expected_entrypoint
        env_values = {
            item["name"]: item["value"]
            for item in service.get("environmentVariables", [])
            if isinstance(item, dict) and "name" in item and "value" in item
        }
        assert env_values.get("DEPARTMENT") == expected_department[service_name]


def test_hosted_agent_project_packaging_includes_required_runtime_assets() -> None:
    root = _repo_root()
    patterns = _load_agentignore_patterns()
    services = _load_azure_yaml()["services"]

    for service_name in ["development-agent", "human-resources-agent", "marketing-agent"]:
        service = services[service_name]
        project = service["project"]
        assert project == ".", "Hosted agent project must be repository root."

        entrypoint = service["codeConfiguration"]["entryPoint"]
        required_paths = [
            "requirements.txt",
            "departments.yaml",
            "src/lifecycle_agent/__init__.py",
            entrypoint,
            f"src/lifecycle_agent/prompts/{service['environmentVariables'][1]['value']}.md",
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
from __future__ import annotations

from pathlib import Path

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _toolbox_path(department: str) -> Path:
    return _repo_root() / "deploy" / "toolboxes" / f"{department}.yaml"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_department_toolboxes_exist() -> None:
    for department in ["development", "human-resources", "marketing"]:
        assert _toolbox_path(department).exists(), (
            f"Missing toolbox definition: deploy/toolboxes/{department}.yaml"
        )


def test_toolbox_connections_are_scoped_to_shared_plus_own_department() -> None:
    expected = {
        "development": {"kb-shared-remote-tool", "kb-development-remote-tool"},
        "human-resources": {"kb-shared-remote-tool", "kb-human-resources-remote-tool"},
        "marketing": {"kb-shared-remote-tool", "kb-marketing-remote-tool"},
    }

    for department, expected_connections in expected.items():
        toolbox = _load_yaml(_toolbox_path(department))
        connections = toolbox.get("connections", [])
        names = {entry.get("name") for entry in connections}

        assert names == expected_connections
        assert len(connections) == 2


def test_toolbox_rejects_duplicate_server_labels_and_api_key_auth() -> None:
    for department in ["development", "human-resources", "marketing"]:
        toolbox = _load_yaml(_toolbox_path(department))

        labels = [entry.get("name") for entry in toolbox.get("connections", [])]
        assert len(labels) == len(set(labels))

        for connection in toolbox.get("connections", []):
            auth_type = str(connection.get("authType", "")).lower()
            assert auth_type != "apikey"

        for tool in toolbox.get("tools", []):
            auth_type = str(tool.get("authType", "")).lower()
            assert auth_type != "apikey"

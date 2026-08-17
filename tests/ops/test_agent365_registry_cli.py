from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from lifecycle_ops.operations.agent365 import registry as target


def test_graph_cli_resolves_the_executable_before_spawning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # On Windows the Azure CLI is 'az.cmd'; subprocess does not apply PATHEXT, so
    # spawning 'az' directly fails with WinError 2.
    monkeypatch.setattr(
        target.shutil,
        "which",
        lambda program: r"C:\tools\az.cmd" if program == "az" else None,
    )
    captured: dict[str, list[str]] = {}

    def fake_run(args, **_kwargs):
        captured["args"] = args
        return subprocess.CompletedProcess(args, 0, "[]", "")

    monkeypatch.setattr(target.subprocess, "run", fake_run)

    client = target.GraphCliClient()
    assert client.find_service_principal("Agent365Observability") is None
    assert captured["args"][0] == r"C:\tools\az.cmd"
    assert captured["args"][1:4] == ["ad", "sp", "list"]


def test_registry_endpoint_falls_back_to_the_azd_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_AI_PROJECT_ENDPOINT", raising=False)
    monkeypatch.setattr(
        target,
        "get_values",
        lambda **_kwargs: {"FOUNDRY_PROJECT_ENDPOINT": "https://azd.example.test/api/projects/p"},
    )

    resolved = target.resolve_value("FOUNDRY_PROJECT_ENDPOINT", target.get_values())

    assert resolved == "https://azd.example.test/api/projects/p"


def test_graph_cli_reports_a_failed_command_as_permission_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(target.shutil, "which", lambda _program: None)

    def fake_run(args, **_kwargs):
        return subprocess.CompletedProcess(args, 1, "", "Insufficient privileges")

    monkeypatch.setattr(target.subprocess, "run", fake_run)

    with pytest.raises(PermissionError, match="Insufficient privileges"):
        target.GraphCliClient().find_service_principal("Agent365Observability")


def test_agent_names_cover_every_department() -> None:
    assert set(target.AGENT_NAMES) == {
        "development-agent",
        "human-resources-agent",
        "marketing-agent",
    }
    assert isinstance(SimpleNamespace(), object)

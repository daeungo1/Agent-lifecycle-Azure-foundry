import subprocess

import pytest

from lifecycle_ops import azd_env


def test_parse_values_preserves_embedded_equals_and_strips_quotes() -> None:
    raw = "FOO=\"alpha=beta\"\nBAR='beta value'\nIGNORED\n"

    assert azd_env.parse_values(raw) == {
        "FOO": "alpha=beta",
        "BAR": "beta value",
    }


def test_get_values_uses_noninteractive_azd_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, 'FOO="alpha"\n', "")

    monkeypatch.setattr(azd_env.subprocess, "run", fake_run)

    assert azd_env.get_values() == {"FOO": "alpha"}
    assert commands == [["azd", "env", "get-values", "--no-prompt"]]


def test_get_values_can_preserve_existing_missing_azd_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command, **kwargs):
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(azd_env.subprocess, "run", fake_run)

    assert azd_env.get_values(ignore_errors=True) == {}
    with pytest.raises(FileNotFoundError):
        azd_env.get_values()


def test_set_value_uses_noninteractive_azd_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(azd_env.subprocess, "run", fake_run)

    azd_env.set_value("TOOLBOX_ENDPOINT_DEVELOPMENT", "https://example.test")

    assert commands == [
        [
            "azd",
            "env",
            "set",
            "TOOLBOX_ENDPOINT_DEVELOPMENT",
            "https://example.test",
            "--no-prompt",
        ]
    ]


def test_resolve_value_matches_azd_mangled_output_casing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # azd restores ARM output names with inconsistent casing, e.g. the Bicep output
    # FOUNDRYIQ_SEARCH_ENDPOINT_SHARED comes back as foundryiQ_SEARCH_ENDPOINT_SHARED.
    monkeypatch.delenv("FOUNDRYIQ_SEARCH_ENDPOINT_SHARED", raising=False)
    values = {"foundryiQ_SEARCH_ENDPOINT_SHARED": "https://shared.search.windows.net"}

    resolved = azd_env.resolve_value("FOUNDRYIQ_SEARCH_ENDPOINT_SHARED", values)

    assert resolved == "https://shared.search.windows.net"


def test_resolve_value_prefers_process_environment_and_ignores_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("searcH_RESOURCE_ID_SHARED", "/from/environment")
    values = {"SEARCH_RESOURCE_ID_SHARED": "/from/azd"}

    assert azd_env.resolve_value("SEARCH_RESOURCE_ID_SHARED", values) == "/from/environment"


def test_resolve_value_returns_default_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MISSING_VALUE", raising=False)

    assert azd_env.resolve_value("MISSING_VALUE", {}) == ""
    assert azd_env.resolve_value("MISSING_VALUE", {}, default="fallback") == "fallback"


def test_resolve_value_skips_empty_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARTIAL_VALUE", "")
    values = {"partiaL_VALUE": "https://example.test"}

    assert azd_env.resolve_value("PARTIAL_VALUE", values) == "https://example.test"


def test_resolve_value_prefers_an_exact_name_over_a_mangled_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider switch can leave both spellings in the same environment.

    azd wrote SEARCH_RESOURCE_ID_SHARED under the bicep provider and
    searcH_RESOURCE_ID_SHARED under the foundry provider. Matching case-insensitively
    alone made the winner depend on dictionary order, which pointed one boundary at a
    decommissioned Search service.
    """
    monkeypatch.delenv("SEARCH_RESOURCE_ID_SHARED", raising=False)
    values = {
        "searcH_RESOURCE_ID_SHARED": "/old/search",
        "SEARCH_RESOURCE_ID_SHARED": "/new/search",
    }

    assert azd_env.resolve_value("SEARCH_RESOURCE_ID_SHARED", values) == "/new/search"


def test_resolve_value_prefers_an_exact_environment_name_over_azd_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_RESOURCE_ID_SHARED", "/from/environment")
    values = {"SEARCH_RESOURCE_ID_SHARED": "/from/azd"}

    assert azd_env.resolve_value("SEARCH_RESOURCE_ID_SHARED", values) == "/from/environment"

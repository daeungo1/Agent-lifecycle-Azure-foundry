import subprocess

import pytest

from lifecycle_ops import azd_env


def test_parse_values_preserves_embedded_equals_and_strips_quotes() -> None:
    raw = 'FOO="alpha=beta"\nBAR=\'beta value\'\nIGNORED\n'

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

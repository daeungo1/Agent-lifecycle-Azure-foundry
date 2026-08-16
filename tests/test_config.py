from pathlib import Path

import pytest

from lifecycle_agent.config import Settings, load_departments, select_department


def test_load_departments_contains_expected_names_and_specialist_counts() -> None:
    configs = load_departments(Path("departments.yaml"))

    assert sorted(configs) == ["development", "human-resources", "marketing"]
    assert all(len(config.specialists) == 2 for config in configs.values())


def test_select_department_raises_for_unknown_name() -> None:
    configs = load_departments(Path("departments.yaml"))

    with pytest.raises(ValueError, match="Unknown department: finance"):
        select_department(configs, "finance")


def test_settings_from_env_raises_single_missing_variables_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_name in [
        "DEPARTMENT",
        "FOUNDRY_PROJECT_ENDPOINT",
        "AZURE_AI_MODEL_DEPLOYMENT_NAME",
        "TOOLBOX_ENDPOINT",
    ]:
        monkeypatch.delenv(env_name, raising=False)

    with pytest.raises(
        ValueError,
        match=(
            "^Missing required environment variables: "
            "DEPARTMENT, FOUNDRY_PROJECT_ENDPOINT, "
            "AZURE_AI_MODEL_DEPLOYMENT_NAME, TOOLBOX_ENDPOINT$"
        ),
    ):
        Settings.from_env()


def test_settings_from_env_sets_responses_protocol_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEPARTMENT", "development")
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://example.services.ai.azure.com/api/projects/test",
    )
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini")
    monkeypatch.setenv("TOOLBOX_ENDPOINT", "https://example.toolbox")

    settings = Settings.from_env()

    assert settings.responses_protocol_version == "2.0.0"
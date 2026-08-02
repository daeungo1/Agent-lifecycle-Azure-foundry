from pathlib import Path

import pytest

from src.lifecycle_agent.config import Settings, load_departments, select_department


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
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ALLOWED_DEPARTMENTS = ("development", "human-resources", "marketing")
REQUIRED_ENV_VARS = (
    "DEPARTMENT",
    "FOUNDRY_PROJECT_ENDPOINT",
    "AZURE_AI_MODEL_DEPLOYMENT_NAME",
    "TOOLBOX_ENDPOINT",
)


@dataclass(frozen=True)
class SpecialistConfig:
    name: str
    description: str


@dataclass(frozen=True)
class DepartmentConfig:
    name: str
    description: str
    prompt_path: Path
    specialists: tuple[SpecialistConfig, ...]


@dataclass(frozen=True)
class Settings:
    department: str
    foundry_project_endpoint: str
    azure_ai_model_deployment_name: str
    toolbox_endpoint: str

    @classmethod
    def from_env(cls) -> "Settings":
        import os

        missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
        if missing:
            missing_list = ", ".join(missing)
            raise ValueError(f"Missing required environment variables: {missing_list}")

        department = os.environ["DEPARTMENT"]
        if department not in ALLOWED_DEPARTMENTS:
            raise ValueError(f"Unknown department: {department}")

        return cls(
            department=department,
            foundry_project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            azure_ai_model_deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            toolbox_endpoint=os.environ["TOOLBOX_ENDPOINT"],
        )


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_departments(path: Path) -> dict[str, DepartmentConfig]:
    full_path = path if path.is_absolute() else _repository_root() / path
    payload = yaml.safe_load(full_path.read_text(encoding="utf-8")) or {}
    departments = payload.get("departments", [])

    result: dict[str, DepartmentConfig] = {}
    for department in departments:
        name = department["name"]
        if name not in ALLOWED_DEPARTMENTS:
            raise ValueError(f"Unknown department: {name}")

        specialists = tuple(
            SpecialistConfig(
                name=specialist["name"],
                description=specialist["description"],
            )
            for specialist in department.get("specialists", [])
        )

        prompt_path = (full_path.parent / department["prompt"]).resolve()
        result[name] = DepartmentConfig(
            name=name,
            description=department["description"],
            prompt_path=prompt_path,
            specialists=specialists,
        )

    expected = sorted(ALLOWED_DEPARTMENTS)
    loaded = sorted(result)
    if loaded != expected:
        raise ValueError(
            f"Expected departments {', '.join(expected)} but found {', '.join(loaded)}"
        )

    return result


def select_department(
    configs: dict[str, DepartmentConfig],
    name: str,
) -> DepartmentConfig:
    if name not in configs:
        raise ValueError(f"Unknown department: {name}")
    return configs[name]
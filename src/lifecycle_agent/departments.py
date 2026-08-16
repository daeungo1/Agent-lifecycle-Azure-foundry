from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


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


def _find_repository_file(path: Path) -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / path
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Could not find repository file: {path}")


def load_departments(
    path: Path | str = Path("departments.yaml"),
) -> dict[str, DepartmentConfig]:
    candidate = Path(path)
    if candidate.is_absolute():
        full_path = candidate
    elif candidate.is_file():
        full_path = candidate.resolve()
    else:
        full_path = _find_repository_file(candidate)

    payload = yaml.safe_load(full_path.read_text(encoding="utf-8")) or {}
    departments = payload.get("departments", [])
    if not departments:
        raise ValueError("departments.yaml must define at least one department")

    result: dict[str, DepartmentConfig] = {}
    for department in departments:
        name = department["name"]
        if name in result:
            raise ValueError(f"Duplicate department: {name}")

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

    return result


def select_department(
    configs: dict[str, DepartmentConfig],
    name: str,
) -> DepartmentConfig:
    if name not in configs:
        raise ValueError(f"Unknown department: {name}")
    return configs[name]

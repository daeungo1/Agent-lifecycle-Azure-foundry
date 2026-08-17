from __future__ import annotations

from pathlib import Path

from lifecycle_agent.departments import load_departments


def department_names() -> tuple[str, ...]:
    return tuple(load_departments())


def require_department(department: str) -> str:
    if department not in load_departments():
        raise ValueError(f"Unknown department: {department}")
    return department


def agent_name(department: str) -> str:
    return f"{require_department(department)}-agent"


def env_suffix(department: str) -> str:
    return require_department(department).replace("-", "_").upper()


def knowledge_path(department: str) -> Path:
    return Path("knowledge") / require_department(department)


def toolbox_name(department: str) -> str:
    return f"{require_department(department)}-knowledge-toolbox"


def toolbox_file(
    department: str,
    root: Path = Path("deploy/toolboxes"),
) -> Path:
    return root / f"{require_department(department)}.yaml"


def continuous_eval_name(department: str) -> str:
    return f"continuous-eval-{require_department(department)}"


def continuous_rule_id(department: str) -> str:
    return f"continuous-response-completed-{require_department(department)}"

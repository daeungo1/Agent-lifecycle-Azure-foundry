from __future__ import annotations

import os
from pathlib import Path

from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential

from .config import Settings, load_departments, select_department
from .observability import configure_observability
from .orchestration import build_department_agent


def _load_department_agent() -> object:
    settings = Settings.from_env()
    departments = load_departments(Path("departments.yaml"))
    department_config = select_department(departments, settings.department)
    configure_observability(settings.department)

    credential = DefaultAzureCredential()
    return build_department_agent(department_config, settings, credential)


def main() -> None:
    agent = _load_department_agent()
    host = ResponsesHostServer(agent)
    port = int(os.getenv("PORT", "8000"))
    host.run(port=port)


if __name__ == "__main__":
    main()

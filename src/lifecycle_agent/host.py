from __future__ import annotations

import os

from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential

from .departments import load_departments, select_department
from .observability import configure_observability
from .orchestration import build_department_agent
from .settings import Settings

DEFAULT_HOST_PORT = 8088


def _load_department_agent(credential: object) -> object:
    settings = Settings.from_env()
    departments = load_departments()
    department_config = select_department(departments, settings.department)
    configure_observability(settings.department)
    return build_department_agent(department_config, settings, credential)


def main() -> None:
    credential = DefaultAzureCredential()
    try:
        agent = _load_department_agent(credential)
        host = ResponsesHostServer(agent)
        port = int(os.getenv("PORT", str(DEFAULT_HOST_PORT)))
        host.run(port=port)
    finally:
        close = getattr(credential, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    main()

from __future__ import annotations

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework_foundry import FoundryChatClient

from .config import DepartmentConfig, Settings
from .toolbox import build_toolbox


def _read_prompt(path) -> str:
    return path.read_text(encoding="utf-8").strip()


def build_department_agent(
    config: DepartmentConfig,
    settings: Settings,
    credential: object,
) -> Agent:
    if len(config.specialists) != 2:
        raise ValueError(
            f"Department '{config.name}' must define exactly two specialists"
        )

    client = FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint,
        model=settings.azure_ai_model_deployment_name,
        credential=credential,
    )

    specialist_tools = []
    for specialist in config.specialists:
        specialist_agent = Agent(
            client,
            instructions=(
                f"You are the {specialist.name} for {config.name}. "
                f"Specialty: {specialist.description}"
            ),
            name=specialist.name,
            description=specialist.description,
            default_options={"store": False},
        )
        specialist_tools.append(
            specialist_agent.as_tool(
                name=specialist.name,
                description=specialist.description,
            )
        )

    toolbox: MCPStreamableHTTPTool = build_toolbox(settings.toolbox_endpoint, credential)

    coordinator = Agent(
        client,
        instructions=_read_prompt(config.prompt_path),
        name=f"{config.name}-coordinator",
        description=config.description,
        tools=[*specialist_tools, toolbox],
        default_options={"store": False},
    )
    return coordinator


__all__ = ["build_department_agent", "build_toolbox"]

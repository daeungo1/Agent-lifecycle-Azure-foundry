from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

AUDIENCE = "https://search.azure.com"

BOUNDARY_TO_ENV_SUFFIX = {
    "shared": "SHARED",
    "development": "DEVELOPMENT",
    "human-resources": "HUMAN_RESOURCES",
    "marketing": "MARKETING",
}


@dataclass(frozen=True)
class ToolboxSpec:
    department: str
    own_boundary: str
    toolbox_name: str
    toolbox_file: str


DEPARTMENT_TOOLBOXES = {
    "development": ToolboxSpec(
        department="development",
        own_boundary="development",
        toolbox_name="development-knowledge-toolbox",
        toolbox_file="toolboxes/development.yaml",
    ),
    "human-resources": ToolboxSpec(
        department="human-resources",
        own_boundary="human-resources",
        toolbox_name="human-resources-knowledge-toolbox",
        toolbox_file="toolboxes/human-resources.yaml",
    ),
    "marketing": ToolboxSpec(
        department="marketing",
        own_boundary="marketing",
        toolbox_name="marketing-knowledge-toolbox",
        toolbox_file="toolboxes/marketing.yaml",
    ),
}


def kb_mcp_endpoint_env_var(boundary: str) -> str:
    return f"KB_MCP_ENDPOINT_{BOUNDARY_TO_ENV_SUFFIX[boundary]}"


def toolbox_endpoint_env_var(department: str) -> str:
    if department not in DEPARTMENT_TOOLBOXES:
        raise ValueError(f"Unknown department: {department}")
    suffix = BOUNDARY_TO_ENV_SUFFIX[department]
    return f"TOOLBOX_ENDPOINT_{suffix}"


def connection_name_for_boundary(boundary: str) -> str:
    return f"kb-{boundary}-remote-tool"


def expected_toolbox_connections(department: str) -> list[str]:
    if department not in DEPARTMENT_TOOLBOXES:
        raise ValueError(f"Unknown department: {department}")

    own_boundary = DEPARTMENT_TOOLBOXES[department].own_boundary
    return [
        connection_name_for_boundary("shared"),
        connection_name_for_boundary(own_boundary),
    ]


def build_connection_create_args(*, connection_name: str, endpoint: str) -> list[str]:
    return [
        "azd",
        "ai",
        "agent",
        "connection",
        "create",
        connection_name,
        "--category",
        "remote-tool",
        "--target",
        endpoint,
        "--auth-type",
        "agentic-identity",
        "--audience",
        AUDIENCE,
        "--no-prompt",
    ]


def build_connection_update_args(*, connection_name: str, endpoint: str) -> list[str]:
    return [
        "azd",
        "ai",
        "agent",
        "connection",
        "update",
        connection_name,
        "--category",
        "remote-tool",
        "--target",
        endpoint,
        "--auth-type",
        "agentic-identity",
        "--audience",
        AUDIENCE,
        "--no-prompt",
    ]


def build_toolbox_create_args(spec: ToolboxSpec) -> list[str]:
    return [
        "azd",
        "ai",
        "toolbox",
        "create",
        spec.toolbox_name,
        "--from-file",
        spec.toolbox_file,
        "--no-prompt",
    ]


def build_toolbox_update_args(spec: ToolboxSpec) -> list[str]:
    return [
        "azd",
        "ai",
        "toolbox",
        "connection",
        "add",
        spec.toolbox_name,
        "--from-file",
        spec.toolbox_file,
        "--no-prompt",
    ]


def build_toolbox_publish_args(toolbox_name: str) -> list[str]:
    return ["azd", "ai", "toolbox", "publish", toolbox_name, "--no-prompt"]


def build_toolbox_show_args(toolbox_name: str) -> list[str]:
    return ["azd", "ai", "toolbox", "show", toolbox_name, "--output", "json", "--no-prompt"]


def build_connection_list_args() -> list[str]:
    return ["azd", "ai", "agent", "connection", "list", "--output", "json", "--no-prompt"]


def build_env_get_values_args() -> list[str]:
    return ["azd", "env", "get-values", "--no-prompt"]


def build_env_set_args(name: str, value: str) -> list[str]:
    return ["azd", "env", "set", name, value, "--no-prompt"]


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]

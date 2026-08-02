from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
        "connection",
        "create",
        connection_name,
        "--kind",
        "remote-tool",
        "--target",
        endpoint,
        "--auth-type",
        "agentic-identity",
        "--audience",
        AUDIENCE,
        "--no-prompt",
    ]


def build_connection_show_args(connection_name: str) -> list[str]:
    return [
        "azd",
        "ai",
        "connection",
        "show",
        connection_name,
        "--output",
        "json",
        "--no-prompt",
    ]


def build_connection_assert_args(connection_name: str | None = None) -> list[str]:
    args = [
        "azd",
        "ai",
        "connection",
        "list",
        "--output",
        "json",
        "--no-prompt",
    ]
    if connection_name:
        args.extend(["--query", f"[?name=='{connection_name}']"])
    return args


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


def build_toolbox_connection_add_args(
    *,
    toolbox_name: str,
    connection_name: str | None = None,
    from_file: str | None = None,
) -> list[str]:
    if bool(connection_name) == bool(from_file):
        raise ValueError("Exactly one of connection_name or from_file must be set")

    return [
        "azd",
        "ai",
        "toolbox",
        "connection",
        "add",
        toolbox_name,
        *( [connection_name] if connection_name else [] ),
        *( ["--from-file", from_file] if from_file else [] ),
        "--output",
        "json",
        "--no-prompt",
    ]


def build_toolbox_connection_remove_args(*, toolbox_name: str, connection_name: str) -> list[str]:
    return [
        "azd",
        "ai",
        "toolbox",
        "connection",
        "remove",
        toolbox_name,
        connection_name,
        "--output",
        "json",
        "--no-prompt",
    ]


def build_toolbox_publish_args(toolbox_name: str, version: str) -> list[str]:
    return ["azd", "ai", "toolbox", "publish", toolbox_name, version, "--no-prompt"]


def build_toolbox_show_args(toolbox_name: str) -> list[str]:
    return ["azd", "ai", "toolbox", "show", toolbox_name, "--output", "json", "--no-prompt"]


def build_connection_list_args() -> list[str]:
    return ["azd", "ai", "connection", "list", "--output", "json", "--no-prompt"]


def build_env_get_values_args() -> list[str]:
    return ["azd", "env", "get-values", "--no-prompt"]


def build_env_set_args(name: str, value: str) -> list[str]:
    return ["azd", "env", "set", name, value, "--no-prompt"]


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def _walk_nodes(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_nodes(child)


def _normalize_connection_name(value: str) -> str:
    if "/" in value:
        return value.rstrip("/").split("/")[-1]
    return value


def extract_toolbox_connection_names(toolbox_show: dict[str, Any] | list[Any]) -> set[str]:
    names: set[str] = set()
    for node in _walk_nodes(toolbox_show):
        if "project_connection_id" in node and isinstance(node["project_connection_id"], str):
            names.add(_normalize_connection_name(node["project_connection_id"]))

        if "connections" in node and isinstance(node["connections"], list):
            for entry in node["connections"]:
                if isinstance(entry, dict):
                    name = entry.get("name")
                    if isinstance(name, str) and name:
                        names.add(_normalize_connection_name(name))
                elif isinstance(entry, str) and entry:
                    names.add(_normalize_connection_name(entry))
    return names


def extract_toolbox_endpoint(
    toolbox_show: dict[str, Any] | list[Any],
    *,
    project_endpoint: str | None = None,
    toolbox_name: str | None = None,
) -> str:
    if project_endpoint and toolbox_name:
        base = project_endpoint.rstrip("/")
        return f"{base}/toolboxes/{toolbox_name}/mcp?api-version=v1"

    return ""


_VERSION_PATTERN = re.compile(r"^(?:v?\d+(?:\.\d+){0,3})(?:[-+][0-9A-Za-z.-]+)?$")


def _is_publishable_version(value: str) -> bool:
    return bool(_VERSION_PATTERN.fullmatch(value.strip()))


def extract_mutation_version(mutation_payload: dict[str, Any] | list[Any]) -> str:
    candidates: list[str] = []
    version_keys = {"version", "toolboxversion", "toolbox_version"}

    def _collect(value: Any, parent_key: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = key.lower()
                if lowered in version_keys and isinstance(child, str):
                    # Ignore generic entries commonly nested under versions lists.
                    if not (lowered == "version" and parent_key.lower() == "versions"):
                        cleaned = child.strip()
                        if _is_publishable_version(cleaned):
                            candidates.append(cleaned)
                _collect(child, key)
            return

        if isinstance(value, list):
            for child in value:
                _collect(child, parent_key)

    _collect(mutation_payload)

    unique = sorted(set(candidates))
    if len(unique) != 1:
        raise ValueError(
            "Mutation payload must contain exactly one publishable toolbox version "
            "under version/toolboxVersion/toolbox_version"
        )

    return unique[0]


def plan_toolbox_reconciliation(*, current: set[str], expected: set[str]) -> dict[str, list[str]]:
    missing = sorted(expected - current)
    extra = sorted(current - expected)
    return {"missing": missing, "extra": extra}


def build_reconciliation_operations(
    *,
    toolbox_name: str,
    current: set[str],
    expected: set[str],
) -> list[dict[str, str]]:
    plan = plan_toolbox_reconciliation(current=current, expected=expected)
    operations: list[dict[str, str]] = []

    for connection_name in plan["missing"]:
        operations.append(
            {
                "action": "add",
                "toolbox": toolbox_name,
                "connection": connection_name,
                "publish": "mutation",
            }
        )

    for connection_name in plan["extra"]:
        operations.append(
            {
                "action": "remove",
                "toolbox": toolbox_name,
                "connection": connection_name,
                "publish": "mutation",
            }
        )

    operations.append({"action": "assert-exact", "toolbox": toolbox_name})
    return operations


def ensure_exact_connection_set(*, toolbox_name: str, expected: set[str], actual: set[str]) -> None:
    plan = plan_toolbox_reconciliation(current=actual, expected=expected)
    if plan["missing"] or plan["extra"]:
        raise ValueError(
            f"Toolbox '{toolbox_name}' connection drift detected: "
            f"missing={plan['missing']} extra={plan['extra']}. "
            "Resolve drift before continuing."
        )

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

from lifecycle_ops.azd_env import get_values, set_value
from lifecycle_ops.naming import (
    department_names,
    env_suffix,
    toolbox_file,
    toolbox_name,
)

AUDIENCE = "https://search.azure.com"

BOUNDARY_TO_ENV_SUFFIX = {
    "shared": "SHARED",
    **{department: env_suffix(department) for department in department_names()},
}


@dataclass(frozen=True)
class ToolboxSpec:
    department: str
    own_boundary: str
    toolbox_name: str
    toolbox_file: str


DEPARTMENT_TOOLBOXES = {
    department: ToolboxSpec(
        department=department,
        own_boundary=department,
        toolbox_name=toolbox_name(department),
        toolbox_file=toolbox_file(department).as_posix(),
    )
    for department in department_names()
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

    spec = DEPARTMENT_TOOLBOXES[department]
    return load_toolbox_connections(repo_root_from_script() / spec.toolbox_file)


def load_toolbox_connections(path: Path) -> list[str]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    connections = payload.get("connections")
    if not isinstance(connections, list) or not connections:
        raise ValueError(f"Toolbox file '{path}' must define non-empty connections")

    names: list[str] = []
    for connection in connections:
        if not isinstance(connection, dict):
            raise ValueError(f"Toolbox file '{path}' has an invalid connection entry")
        name = connection.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Toolbox file '{path}' has a connection without a name")
        names.append(name.strip())
    return names


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
        *([connection_name] if connection_name else []),
        *(["--from-file", from_file] if from_file else []),
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
    return Path(__file__).resolve().parents[3]


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


def _run_raw(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _run_json(
    command: list[str],
    *,
    allow_failure: bool = False,
) -> Any:
    try:
        output = _run_raw(command)
    except subprocess.CalledProcessError:
        if allow_failure:
            return None
        raise
    if not output.strip():
        return None
    return json.loads(output)


def _ensure_azd_support() -> None:
    try:
        _run_raw(["azd", "ai", "toolbox", "--help", "--no-prompt"])
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "The current azd installation does not support 'azd ai toolbox'. "
            "Install or upgrade the azd AI extension before running this command."
        ) from exc
    try:
        _run_raw(["azd", "ai", "connection", "--help", "--no-prompt"])
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "The current azd installation does not support 'azd ai connection'. "
            "Install or upgrade the azd AI extension before running this command."
        ) from exc


def _normalize_alphanumeric(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", value).lower()


def _normalize_endpoint(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
        if not parsed.scheme or not parsed.netloc:
            return raw.rstrip("/")
        host = parsed.hostname.lower() if parsed.hostname else ""
        is_default_port = (parsed.scheme.lower(), parsed.port) in {
            ("http", 80),
            ("https", 443),
        }
        port = f":{parsed.port}" if parsed.port and not is_default_port else ""
        path = parsed.path.rstrip("/") if len(parsed.path) > 1 else parsed.path
        return urlunsplit((parsed.scheme.lower(), f"{host}{port}", path, parsed.query, ""))
    except ValueError:
        return raw.rstrip("/")


def _connection_field(details: dict[str, Any], *names: str) -> str:
    for name in names:
        value = details.get(name)
        if value:
            return str(value)
    return ""


def validate_remote_tool_connection(
    *,
    connection_name: str,
    expected_target: str,
    details: dict[str, Any],
) -> None:
    kind = _connection_field(details, "kind", "category")
    target = _connection_field(details, "target", "endpoint", "url")
    auth_type = _connection_field(details, "authType", "auth_type")
    audience = _connection_field(details, "audience")
    drift: list[str] = []

    if _normalize_alphanumeric(kind) != "remotetool":
        drift.append(f"kind='{kind}' expected='remote-tool'")
    if _normalize_endpoint(target) != _normalize_endpoint(expected_target):
        drift.append(f"target='{target}' expected='{expected_target}'")
    if _normalize_alphanumeric(auth_type) != "agenticidentity":
        drift.append(f"authType='{auth_type}' expected='agentic-identity'")
    if _normalize_endpoint(audience) != _normalize_endpoint(AUDIENCE):
        drift.append(f"audience='{audience}' expected='{AUDIENCE}'")

    if drift:
        raise ValueError(
            f"Connection '{connection_name}' drift detected. "
            + "; ".join(drift)
            + ". Fix the connection manually or remove/recreate it, then rerun."
        )


def _connection_exists(payload: Any, connection_name: str) -> bool:
    return any(
        node.get("name") == connection_name
        for node in _walk_nodes(payload)
        if isinstance(node.get("name"), str)
    )


def ensure_remote_tool_connection(
    *,
    connection_name: str,
    target: str,
    dry_run: bool = False,
) -> None:
    connections = _run_json(build_connection_list_args())
    if not _connection_exists(connections, connection_name):
        if not dry_run:
            _run_raw(
                build_connection_create_args(
                    connection_name=connection_name,
                    endpoint=target,
                )
            )
        return

    details = _run_json(build_connection_show_args(connection_name))
    if not isinstance(details, dict):
        raise ValueError(
            f"Connection '{connection_name}' exists but details could not be loaded "
            "with 'azd ai connection show'. Resolve manually and rerun."
        )
    validate_remote_tool_connection(
        connection_name=connection_name,
        expected_target=target,
        details=details,
    )


def _publish_mutation(*, toolbox_name: str, mutation: Any) -> None:
    if not isinstance(mutation, (dict, list)):
        raise ValueError("Toolbox connection mutation did not return JSON")
    version = extract_mutation_version(mutation)
    _run_raw(build_toolbox_publish_args(toolbox_name, version))


def upsert_toolbox(
    *,
    spec: ToolboxSpec,
    project_endpoint: str,
    dry_run: bool = False,
) -> dict[str, str]:
    expected = set(expected_toolbox_connections(spec.department))
    show_result = _run_json(
        build_toolbox_show_args(spec.toolbox_name),
        allow_failure=True,
    )

    if show_result is None:
        if not dry_run:
            _run_raw(build_toolbox_create_args(spec))
    else:
        current = extract_toolbox_connection_names(show_result)
        plan = plan_toolbox_reconciliation(current=current, expected=expected)

        for connection_name in plan["missing"]:
            if not dry_run:
                mutation = _run_json(
                    build_toolbox_connection_add_args(
                        toolbox_name=spec.toolbox_name,
                        connection_name=connection_name,
                    )
                )
                _publish_mutation(toolbox_name=spec.toolbox_name, mutation=mutation)
            show_result = _run_json(build_toolbox_show_args(spec.toolbox_name))
            current = extract_toolbox_connection_names(show_result)

        for connection_name in plan_toolbox_reconciliation(
            current=current,
            expected=expected,
        )["extra"]:
            if len(current) <= 1:
                raise ValueError(
                    f"Refusing to remove '{connection_name}' from '{spec.toolbox_name}' "
                    "because toolbox cannot be left with zero tools."
                )
            if not dry_run:
                mutation = _run_json(
                    build_toolbox_connection_remove_args(
                        toolbox_name=spec.toolbox_name,
                        connection_name=connection_name,
                    )
                )
                _publish_mutation(toolbox_name=spec.toolbox_name, mutation=mutation)
            show_result = _run_json(build_toolbox_show_args(spec.toolbox_name))
            current = extract_toolbox_connection_names(show_result)

        ensure_exact_connection_set(
            toolbox_name=spec.toolbox_name,
            expected=expected,
            actual=current,
        )

    endpoint = ""
    if not dry_run:
        published = _run_json(build_toolbox_show_args(spec.toolbox_name))
        actual = extract_toolbox_connection_names(published)
        ensure_exact_connection_set(
            toolbox_name=spec.toolbox_name,
            expected=expected,
            actual=actual,
        )
        if not project_endpoint:
            raise ValueError(
                "Missing required FOUNDRY_PROJECT_ENDPOINT for deterministic "
                "toolbox endpoint construction."
            )
        endpoint = extract_toolbox_endpoint(
            published,
            project_endpoint=project_endpoint,
            toolbox_name=spec.toolbox_name,
        )
        set_value(toolbox_endpoint_env_var(spec.department), endpoint)

    return {
        "department": spec.department,
        "toolbox_name": spec.toolbox_name,
        "endpoint": endpoint,
    }


def configure_toolboxes(*, dry_run: bool = False) -> list[dict[str, str]]:
    _ensure_azd_support()
    env_values = get_values()
    boundaries = ("shared", *department_names())
    for boundary in boundaries:
        env_name = kb_mcp_endpoint_env_var(boundary)
        endpoint = env_values.get(env_name, "")
        if not endpoint:
            raise ValueError(f"Missing required azd environment value: {env_name}")

    for boundary in boundaries:
        ensure_remote_tool_connection(
            connection_name=connection_name_for_boundary(boundary),
            target=env_values[kb_mcp_endpoint_env_var(boundary)],
            dry_run=dry_run,
        )

    project_endpoint = env_values.get("FOUNDRY_PROJECT_ENDPOINT", "")
    return [
        upsert_toolbox(
            spec=DEPARTMENT_TOOLBOXES[department],
            project_endpoint=project_endpoint,
            dry_run=dry_run,
        )
        for department in department_names()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or reconcile Foundry toolboxes.")
    parser.add_argument("--what-if-only", action="store_true")
    args = parser.parse_args(argv)
    configure_toolboxes(dry_run=args.what_if_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

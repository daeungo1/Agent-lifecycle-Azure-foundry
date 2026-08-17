from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from lifecycle_ops.azd_env import parse_values, resolve_value
from lifecycle_ops.naming import agent_name as derive_agent_name
from lifecycle_ops.naming import (
    department_names,
    env_suffix,
)

ROLE_NAME = "Search Index Data Reader"

DEPARTMENT_BY_AGENT = {
    derive_agent_name(department): department for department in department_names()
}

KNOWN_BOUNDARIES = ["shared", *department_names()]
BOUNDARY_TO_ENV_SUFFIX = {
    "shared": "SHARED",
    **{department: env_suffix(department) for department in department_names()},
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def search_resource_id_env_var(boundary: str) -> str:
    return f"SEARCH_RESOURCE_ID_{BOUNDARY_TO_ENV_SUFFIX[boundary]}"


def _parse_azd_env_values(raw_env: str) -> dict[str, str]:
    return parse_values(raw_env)


def _load_active_azd_environment() -> dict[str, str]:
    try:
        result = subprocess.run(
            ["azd", "env", "get-values", "--no-prompt"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {}
    return _parse_azd_env_values(result.stdout)


def _run_json_command(args: list[str]) -> Any:
    # Windows ships the Azure CLI as 'az.cmd'; subprocess does not apply PATHEXT,
    # so the program has to be resolved to a real path before spawning.
    if args:
        args = [shutil.which(args[0]) or args[0], *args[1:]]
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def build_agent_show_args(agent_name: str) -> list[str]:
    return [
        "azd",
        "ai",
        "agent",
        "show",
        agent_name,
        "--output",
        "json",
        "--no-prompt",
    ]


def extract_agent_principal_id(payload: dict[str, Any], agent_name: str) -> str:
    identity = payload.get("instance_identity")
    principal_id = identity.get("principal_id") if isinstance(identity, dict) else None
    if not principal_id:
        raise RuntimeError(f"Missing instance identity principal ID for agent: {agent_name}")
    return str(principal_id)


def _get_project_endpoint(azd_env: dict[str, str]) -> str:
    endpoint = resolve_value("AZURE_AI_PROJECT_ENDPOINT", azd_env) or resolve_value(
        "FOUNDRY_PROJECT_ENDPOINT", azd_env
    )
    if not endpoint:
        raise ValueError(
            "Missing required environment value: AZURE_AI_PROJECT_ENDPOINT or "
            "FOUNDRY_PROJECT_ENDPOINT"
        )
    return endpoint


def _get_search_resource_ids(azd_env: dict[str, str]) -> dict[str, str]:
    resource_ids: dict[str, str] = {}
    missing: list[str] = []

    for boundary in KNOWN_BOUNDARIES:
        env_name = search_resource_id_env_var(boundary)
        value = resolve_value(env_name, azd_env)
        if not value:
            missing.append(env_name)
        resource_ids[boundary] = value

    if missing:
        raise ValueError("Missing required Search resource ID variables: " + ", ".join(missing))

    return resource_ids


def get_agent_principal_ids(_project_endpoint: str) -> dict[str, str]:
    principal_ids: dict[str, str] = {}
    for agent_name in DEPARTMENT_BY_AGENT:
        payload = _run_json_command(build_agent_show_args(agent_name))
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unable to load deployed agent: {agent_name}")
        principal_ids[agent_name] = extract_agent_principal_id(payload, agent_name)

    return principal_ids


def build_role_assignment_list_args(*, principal_id: str, scope: str, role_name: str) -> list[str]:
    return [
        "az",
        "role",
        "assignment",
        "list",
        "--assignee-object-id",
        principal_id,
        "--scope",
        scope,
        "--role",
        role_name,
        "--output",
        "json",
    ]


def build_role_assignment_create_args(
    *,
    principal_id: str,
    scope: str,
    role_id_or_name: str,
) -> list[str]:
    return [
        "az",
        "role",
        "assignment",
        "create",
        "--assignee-object-id",
        principal_id,
        "--scope",
        scope,
        "--role",
        role_id_or_name,
        "--output",
        "json",
    ]


def resolve_role_definition_id(role_name: str) -> str:
    role_defs = _run_json_command(
        [
            "az",
            "role",
            "definition",
            "list",
            "--name",
            role_name,
            "--output",
            "json",
        ]
    )
    if not role_defs:
        raise RuntimeError(f"Role definition not found: {role_name}")

    role_def = role_defs[0]
    role_guid = role_def.get("name")
    if role_guid:
        return role_guid

    role_id = role_def.get("id")
    if role_id:
        return role_id

    raise RuntimeError(f"Role definition payload did not contain id/name: {role_name}")


def build_desired_scope_matrix(
    *,
    principal_ids: dict[str, str],
    resource_ids: dict[str, str],
) -> dict[str, dict[str, Any]]:
    matrix: dict[str, dict[str, Any]] = {}
    for agent_name, department in DEPARTMENT_BY_AGENT.items():
        matrix[agent_name] = {
            "department": department,
            "principalId": principal_ids[agent_name],
            "allowedScopes": [resource_ids["shared"], resource_ids[department]],
        }
    return matrix


def _normalize_scope(scope: str) -> str:
    return scope.rstrip("/").lower()


def detect_forbidden_assignments(
    *,
    desired_matrix: dict[str, dict[str, Any]],
    existing_assignments: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    forbidden: list[dict[str, Any]] = []
    for agent_name, desired in desired_matrix.items():
        allowed = {_normalize_scope(scope) for scope in desired["allowedScopes"]}
        for assignment in existing_assignments.get(agent_name, []):
            if str(assignment.get("roleDefinitionName", "")) != ROLE_NAME:
                continue

            scope = str(assignment.get("scope", ""))
            if _normalize_scope(scope) in allowed:
                continue

            forbidden.append(
                {
                    "agentName": agent_name,
                    "department": desired["department"],
                    "scope": scope,
                    "roleDefinitionName": assignment.get("roleDefinitionName"),
                }
            )
    return forbidden


def _collect_existing_assignments(
    *,
    desired_matrix: dict[str, dict[str, Any]],
    all_known_scopes: list[str],
) -> dict[str, list[dict[str, Any]]]:
    all_assignments: dict[str, list[dict[str, Any]]] = {}

    for agent_name, desired in desired_matrix.items():
        principal_id = desired["principalId"]
        rows: list[dict[str, Any]] = []
        for scope in all_known_scopes:
            args = build_role_assignment_list_args(
                principal_id=principal_id,
                scope=scope,
                role_name=ROLE_NAME,
            )
            assignments = _run_json_command(args) or []
            rows.extend(assignments)
        all_assignments[agent_name] = rows

    return all_assignments


def _calculate_missing_assignments(
    *,
    desired_matrix: dict[str, dict[str, Any]],
    existing_assignments: dict[str, list[dict[str, Any]]],
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for agent_name, desired in desired_matrix.items():
        existing_scopes = {
            _normalize_scope(str(assignment.get("scope", "")))
            for assignment in existing_assignments.get(agent_name, [])
            if str(assignment.get("roleDefinitionName", "")) == ROLE_NAME
        }

        for scope in desired["allowedScopes"]:
            if _normalize_scope(scope) not in existing_scopes:
                missing.append(
                    {
                        "agentName": agent_name,
                        "principalId": desired["principalId"],
                        "scope": scope,
                    }
                )
    return missing


def apply_search_rbac(*, dry_run: bool = False) -> dict[str, Any]:
    azd_env = _load_active_azd_environment()
    project_endpoint = _get_project_endpoint(azd_env)
    resource_ids = _get_search_resource_ids(azd_env)
    principal_ids = get_agent_principal_ids(project_endpoint)

    desired_matrix = build_desired_scope_matrix(
        principal_ids=principal_ids,
        resource_ids=resource_ids,
    )

    all_known_scopes = [resource_ids[boundary] for boundary in KNOWN_BOUNDARIES]
    existing_assignments = _collect_existing_assignments(
        desired_matrix=desired_matrix,
        all_known_scopes=all_known_scopes,
    )

    planned_assignments = _calculate_missing_assignments(
        desired_matrix=desired_matrix,
        existing_assignments=existing_assignments,
    )

    role_definition_id = resolve_role_definition_id(ROLE_NAME)
    created_assignments: list[dict[str, Any]] = []

    if not dry_run:
        for pending in planned_assignments:
            args = build_role_assignment_create_args(
                principal_id=pending["principalId"],
                scope=pending["scope"],
                role_id_or_name=role_definition_id,
            )
            created = _run_json_command(args)
            if created:
                created_assignments.append(created)

        existing_assignments = _collect_existing_assignments(
            desired_matrix=desired_matrix,
            all_known_scopes=all_known_scopes,
        )

    remaining_missing_assignments = _calculate_missing_assignments(
        desired_matrix=desired_matrix,
        existing_assignments=existing_assignments,
    )

    if dry_run:
        remaining_missing_assignments = list(planned_assignments)

    forbidden_assignments = detect_forbidden_assignments(
        desired_matrix=desired_matrix,
        existing_assignments=existing_assignments,
    )

    return {
        "role": {
            "name": ROLE_NAME,
            "definitionId": role_definition_id,
        },
        "resourceIds": resource_ids,
        "desiredMatrix": desired_matrix,
        "plannedAssignments": planned_assignments,
        "missingAssignments": remaining_missing_assignments,
        "createdAssignments": created_assignments,
        "forbiddenAssignments": forbidden_assignments,
        "dryRun": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Grant least-privilege Search Index Data Reader RBAC to hosted agent identities."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute matrix/report without creating any role assignments.",
    )
    parser.add_argument(
        "--report-path",
        default=str(_repo_root() / "rbac-report.json"),
        help="Path for JSON RBAC report output.",
    )
    args = parser.parse_args()

    report = apply_search_rbac(dry_run=args.dry_run)
    report_json = json.dumps(report, indent=2, sort_keys=True)
    print(report_json)

    report_path = Path(args.report_path)
    report_path.write_text(report_json, encoding="utf-8")

    if report["forbiddenAssignments"]:
        return 2
    if (not args.dry_run) and report["missingAssignments"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

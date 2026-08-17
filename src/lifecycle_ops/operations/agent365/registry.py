from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from lifecycle_ops.azd_env import get_values, resolve_value
from lifecycle_ops.naming import agent_name as derive_agent_name
from lifecycle_ops.naming import department_names

AGENT365_SERVICE_PRINCIPAL_NAME = "Agent365Observability"
AGENT365_APP_ROLE_VALUE = "Agent365.Observability.OtelWrite"
AGENT_NAMES = [derive_agent_name(department) for department in department_names()]


@dataclass
class GraphCliClient:
    def _run_json(self, args: list[str]) -> Any:
        # Windows ships the Azure CLI as 'az.cmd'; subprocess does not apply PATHEXT,
        # so the program has to be resolved to a real path before spawning.
        resolved = [shutil.which(args[0]) or args[0], *args[1:]]
        completed = subprocess.run(resolved, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise PermissionError(completed.stderr.strip() or "Graph CLI command failed")
        stdout = completed.stdout.strip()
        if not stdout:
            return None
        return json.loads(stdout)

    def find_service_principal(self, display_name: str) -> dict[str, Any] | None:
        payload = self._run_json(
            [
                "az",
                "ad",
                "sp",
                "list",
                "--display-name",
                display_name,
                "--output",
                "json",
            ]
        )
        if isinstance(payload, list) and payload:
            return payload[0]
        return None

    def find_app_role(self, service_principal_id: str, role_value: str) -> dict[str, Any] | None:
        payload = self._run_json(
            [
                "az",
                "ad",
                "sp",
                "show",
                "--id",
                service_principal_id,
                "--output",
                "json",
            ]
        )
        if not isinstance(payload, dict):
            return None

        for role in payload.get("appRoles", []):
            if isinstance(role, dict) and role.get("value") == role_value:
                return role
        return None

    def has_app_role_assignment(
        self,
        *,
        principal_object_id: str,
        resource_service_principal_id: str,
        app_role_id: str,
    ) -> bool:
        payload = self._run_json(
            [
                "az",
                "rest",
                "--method",
                "GET",
                "--url",
                f"https://graph.microsoft.com/v1.0/servicePrincipals/{principal_object_id}/appRoleAssignments",
                "--output",
                "json",
            ]
        )
        assignments = payload.get("value", []) if isinstance(payload, dict) else []
        for assignment in assignments:
            if not isinstance(assignment, dict):
                continue
            if (
                assignment.get("resourceId") == resource_service_principal_id
                and assignment.get("appRoleId") == app_role_id
            ):
                return True
        return False

    def grant_app_role_assignment(
        self,
        *,
        principal_object_id: str,
        resource_service_principal_id: str,
        app_role_id: str,
    ) -> None:
        body = json.dumps(
            {
                "principalId": principal_object_id,
                "resourceId": resource_service_principal_id,
                "appRoleId": app_role_id,
            }
        )
        self._run_json(
            [
                "az",
                "rest",
                "--method",
                "POST",
                "--url",
                f"https://graph.microsoft.com/v1.0/servicePrincipals/{principal_object_id}/appRoleAssignments",
                "--body",
                body,
                "--output",
                "json",
            ]
        )


def _status(status: str, reason: str) -> dict[str, str]:
    return {
        "status": status,
        "reason": reason,
    }


def _extract_principal_id(identity: Any) -> str | None:
    if identity is None:
        return None
    if isinstance(identity, dict):
        principal_id = identity.get("principal_id") or identity.get("principalId")
        if isinstance(principal_id, str) and principal_id:
            return principal_id
        return None

    principal_id = getattr(identity, "principal_id", None) or getattr(
        identity,
        "principalId",
        None,
    )
    if isinstance(principal_id, str) and principal_id:
        return principal_id
    return None


def _resolve_hosted_agent_object_ids(
    project_endpoint: str,
    explicit_object_ids: dict[str, str] | None = None,
) -> dict[str, str]:
    explicit_object_ids = explicit_object_ids or {}
    if explicit_object_ids:
        resolved: dict[str, str] = {}
        for agent_name, object_id in explicit_object_ids.items():
            cleaned = object_id.strip()
            if not cleaned:
                raise RuntimeError(f"Hosted agent object id for '{agent_name}' is empty.")
            resolved[agent_name] = cleaned
        return resolved

    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    project_client = None
    try:
        project_client = AIProjectClient(endpoint=project_endpoint, credential=credential)
        agents_api = getattr(project_client, "agents", None)
        get_fn = getattr(agents_api, "get", None) if agents_api is not None else None
        if not callable(get_fn):
            raise RuntimeError("AIProjectClient.agents.get(agent_name=...) is unavailable.")

        resolved = {}
        for agent_name in AGENT_NAMES:
            agent = get_fn(agent_name=agent_name)
            identity = getattr(agent, "instance_identity", None)
            principal_id = _extract_principal_id(identity)
            if not principal_id:
                raise RuntimeError(
                    f"Missing instance_identity.principal_id for hosted agent '{agent_name}'."
                )
            resolved[agent_name] = principal_id
        return resolved
    finally:
        if project_client is not None:
            close_project_client = getattr(project_client, "close", None)
            if callable(close_project_client):
                close_project_client()
        close_credential = getattr(credential, "close", None)
        if callable(close_credential):
            close_credential()


def verify_agent365_registry_status(
    *,
    graph_client: Any,
    hosted_agent_object_ids_by_name: dict[str, str],
    prerequisites_claimed: bool = False,
    grant: bool = False,
) -> dict[str, str]:
    if not hosted_agent_object_ids_by_name:
        return _status("failed", "No hosted agent object IDs were provided for verification.")

    for agent_name, object_id in hosted_agent_object_ids_by_name.items():
        if not object_id.strip():
            return _status(
                "failed",
                f"Hosted agent object id for '{agent_name}' is empty or malformed.",
            )

    try:
        service_principal = graph_client.find_service_principal(AGENT365_SERVICE_PRINCIPAL_NAME)
    except json.JSONDecodeError:
        return _status("failed", "Malformed Graph response while locating Agent365Observability.")
    except PermissionError as exc:
        if prerequisites_claimed:
            return _status(
                "failed",
                f"Cannot read directory objects for Agent365Observability: {exc}",
            )
        return _status(
            "prerequisite-skipped",
            f"Cannot read directory objects for Agent365Observability: {exc}",
        )
    except OSError as exc:
        return _status(
            "failed",
            f"Network or process error while locating service principal: {exc}",
        )

    if not service_principal:
        return _status(
            "prerequisite-skipped",
            "Agent365Observability service principal is not available in this "
            "tenant or license scope.",
        )

    service_principal_id = service_principal.get("id", "")
    if not isinstance(service_principal_id, str) or not service_principal_id:
        return _status("failed", "Agent365Observability service principal metadata is malformed.")

    try:
        role = graph_client.find_app_role(service_principal_id, AGENT365_APP_ROLE_VALUE)
    except json.JSONDecodeError:
        return _status("failed", "Malformed Graph response while reading app role metadata.")
    except PermissionError as exc:
        if prerequisites_claimed:
            return _status(
                "failed",
                f"Cannot read app role metadata for Agent365Observability: {exc}",
            )
        return _status(
            "prerequisite-skipped",
            f"Cannot read app role metadata for Agent365Observability: {exc}",
        )
    except OSError as exc:
        return _status("failed", f"Network or process error while reading app role metadata: {exc}")

    if not role:
        return _status(
            "prerequisite-skipped",
            "Agent365.Observability.OtelWrite app role is unavailable for Agent365Observability.",
        )

    app_role_id = role.get("id", "")
    if not isinstance(app_role_id, str) or not app_role_id:
        return _status("failed", "Agent365Observability app role metadata is malformed.")

    agent_states: dict[str, str] = {}
    for agent_name, hosted_agent_object_id in hosted_agent_object_ids_by_name.items():
        try:
            has_assignment = graph_client.has_app_role_assignment(
                principal_object_id=hosted_agent_object_id,
                resource_service_principal_id=service_principal_id,
                app_role_id=app_role_id,
            )
        except (PermissionError, OSError):
            return _status(
                "failed",
                f"Unable to verify Agent365 role assignment for '{agent_name}'.",
            )
        except json.JSONDecodeError:
            return _status(
                "failed",
                f"Malformed Graph response while checking role assignment for '{agent_name}'.",
            )

        if has_assignment:
            agent_states[agent_name] = "verified"
            continue

        if grant:
            try:
                graph_client.grant_app_role_assignment(
                    principal_object_id=hosted_agent_object_id,
                    resource_service_principal_id=service_principal_id,
                    app_role_id=app_role_id,
                )
                has_assignment = graph_client.has_app_role_assignment(
                    principal_object_id=hosted_agent_object_id,
                    resource_service_principal_id=service_principal_id,
                    app_role_id=app_role_id,
                )
            except (PermissionError, OSError):
                return _status(
                    "failed",
                    f"Unable to grant Agent365 role assignment for '{agent_name}'.",
                )
            except json.JSONDecodeError:
                return _status(
                    "failed",
                    f"Malformed Graph response while granting role assignment for '{agent_name}'.",
                )
            if has_assignment:
                agent_states[agent_name] = "verified"
                continue

        if prerequisites_claimed:
            agent_states[agent_name] = "failed"
        else:
            agent_states[agent_name] = "prerequisite-skipped"

    if any(state == "failed" for state in agent_states.values()):
        return _status(
            "failed",
            "Agent365 role assignment drift detected: expected assignment is missing.",
        )

    if any(state == "prerequisite-skipped" for state in agent_states.values()):
        return _status(
            "prerequisite-skipped",
            "Agent365 role assignment is not present for one or more hosted agents. "
            "Re-run with --grant if you have directory permissions.",
        )

    return _status("verified", "Required Agent365 role assignment is present for all agents.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Agent 365 observability app role assignment"
    )
    parser.add_argument("--foundry-project-endpoint")
    parser.add_argument("--hosted-agent-object-id")
    parser.add_argument("--development-agent-object-id")
    parser.add_argument("--human-resources-agent-object-id")
    parser.add_argument("--marketing-agent-object-id")
    parser.add_argument("--prerequisites-claimed", action="store_true")
    parser.add_argument("--grant", action="store_true")
    args = parser.parse_args()

    explicit_ids: dict[str, str] = {}
    if args.hosted_agent_object_id:
        explicit_ids["development-agent"] = args.hosted_agent_object_id
    if args.development_agent_object_id:
        explicit_ids["development-agent"] = args.development_agent_object_id
    if args.human_resources_agent_object_id:
        explicit_ids["human-resources-agent"] = args.human_resources_agent_object_id
    if args.marketing_agent_object_id:
        explicit_ids["marketing-agent"] = args.marketing_agent_object_id

    azd_env = get_values(ignore_errors=True)
    endpoint = (
        args.foundry_project_endpoint
        or resolve_value("FOUNDRY_PROJECT_ENDPOINT", azd_env)
        or resolve_value("AZURE_AI_PROJECT_ENDPOINT", azd_env)
    )

    if not explicit_ids and not endpoint:
        status = _status(
            "failed",
            "Set FOUNDRY_PROJECT_ENDPOINT (preferred) or AZURE_AI_PROJECT_ENDPOINT, "
            "or pass explicit hosted agent object IDs.",
        )
        print(json.dumps(status, indent=2))
        return 2

    try:
        hosted_agent_object_ids_by_name = _resolve_hosted_agent_object_ids(
            endpoint,
            explicit_object_ids=explicit_ids or None,
        )
    except Exception as exc:
        status = _status("failed", f"Unable to resolve hosted agent identities: {exc}")
        print(json.dumps(status, indent=2))
        return 2

    status = verify_agent365_registry_status(
        graph_client=GraphCliClient(),
        hosted_agent_object_ids_by_name=hosted_agent_object_ids_by_name,
        prerequisites_claimed=args.prerequisites_claimed,
        grant=args.grant,
    )
    print(json.dumps(status, indent=2))
    if status["status"] == "failed":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

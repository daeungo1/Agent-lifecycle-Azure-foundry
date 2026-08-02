from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from typing import Any

AGENT365_SERVICE_PRINCIPAL_NAME = "Agent365Observability"
AGENT365_APP_ROLE_VALUE = "Agent365.Observability.OtelWrite"


@dataclass
class GraphCliClient:
    def _run_json(self, args: list[str]) -> Any:
        completed = subprocess.run(args, capture_output=True, text=True, check=False)
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


def verify_agent365_registry_status(
    *,
    graph_client: Any,
    hosted_agent_object_id: str,
    prerequisites_claimed: bool = False,
    grant: bool = False,
) -> dict[str, str]:
    if not hosted_agent_object_id.strip():
        return _status("failed", "Hosted agent object id is empty or malformed.")

    try:
        service_principal = graph_client.find_service_principal(AGENT365_SERVICE_PRINCIPAL_NAME)
    except PermissionError as exc:
        return _status(
            "prerequisite-skipped",
            f"Cannot read directory objects for Agent365Observability: {exc}",
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

    role = graph_client.find_app_role(service_principal_id, AGENT365_APP_ROLE_VALUE)
    if not role:
        return _status(
            "prerequisite-skipped",
            "Agent365.Observability.OtelWrite app role is unavailable for Agent365Observability.",
        )

    app_role_id = role.get("id", "")
    if not isinstance(app_role_id, str) or not app_role_id:
        return _status("failed", "Agent365Observability app role metadata is malformed.")

    if graph_client.has_app_role_assignment(
        principal_object_id=hosted_agent_object_id,
        resource_service_principal_id=service_principal_id,
        app_role_id=app_role_id,
    ):
        return _status(
            "verified",
            "Required Agent365.Observability.OtelWrite assignment is present.",
        )

    if grant:
        try:
            graph_client.grant_app_role_assignment(
                principal_object_id=hosted_agent_object_id,
                resource_service_principal_id=service_principal_id,
                app_role_id=app_role_id,
            )
        except PermissionError as exc:
            return _status(
                "failed" if prerequisites_claimed else "prerequisite-skipped",
                f"Unable to grant Agent365.Observability.OtelWrite assignment: {exc}",
            )

        if graph_client.has_app_role_assignment(
            principal_object_id=hosted_agent_object_id,
            resource_service_principal_id=service_principal_id,
            app_role_id=app_role_id,
        ):
            return _status("verified", "App role assignment granted and verified.")

    if prerequisites_claimed:
        return _status(
            "failed",
            "Agent365 role assignment drift detected: expected assignment is missing.",
        )

    return _status(
        "prerequisite-skipped",
        "Agent365 role assignment is not present. Re-run with --grant if you "
        "have directory permissions.",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Agent 365 observability app role assignment"
    )
    parser.add_argument("--hosted-agent-object-id", required=True)
    parser.add_argument("--prerequisites-claimed", action="store_true")
    parser.add_argument("--grant", action="store_true")
    args = parser.parse_args()

    status = verify_agent365_registry_status(
        graph_client=GraphCliClient(),
        hosted_agent_object_id=args.hosted_agent_object_id,
        prerequisites_claimed=args.prerequisites_claimed,
        grant=args.grant,
    )
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

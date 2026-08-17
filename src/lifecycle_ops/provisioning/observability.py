"""Provision Application Insights and connect it to the Foundry project.

`azd provision` cannot do this. The `microsoft.foundry` provider synthesises its own
ARM template containing only the Foundry account, project and model deployment, so
resources declared in `deploy/infra/main.bicep` never reach ARM. Observability is
therefore provisioned from the postprovision hook, the same way knowledge bases,
toolboxes and RBAC already are.

The Foundry portal renders agent traces from the Application Insights resource
connected to the project, so both the resource and the connection are required.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lifecycle_ops.azd_env import get_values, resolve_value, set_value

ACCOUNT_PREFIX = "cog-"
APPLICATION_INSIGHTS_PREFIX = "appi-"
LOG_ANALYTICS_PREFIX = "log-"
CONNECTION_NAME = "appinsights-connection"
CONNECTION_API_VERSION = "2025-04-01-preview"
CONNECTION_STRING_ENV_VAR = "APPLICATIONINSIGHTS_CONNECTION_STRING"
MODULE_PATH = "deploy/infra/modules/observability.bicep"


@dataclass(frozen=True)
class ResourceNames:
    application_insights: str
    log_analytics_workspace: str


def build_resource_names(account_name: str) -> ResourceNames:
    if not account_name.startswith(ACCOUNT_PREFIX):
        raise ValueError(
            f"Foundry account name '{account_name}' does not start with '{ACCOUNT_PREFIX}'."
        )

    token = account_name[len(ACCOUNT_PREFIX) :]
    return ResourceNames(
        application_insights=f"{APPLICATION_INSIGHTS_PREFIX}{token}",
        log_analytics_workspace=f"{LOG_ANALYTICS_PREFIX}{token}",
    )


def build_deployment_args(
    *,
    resource_group: str,
    location: str,
    names: ResourceNames,
) -> list[str]:
    return [
        "az",
        "deployment",
        "group",
        "create",
        "--resource-group",
        resource_group,
        "--template-file",
        MODULE_PATH,
        "--parameters",
        f"location={location}",
        "--parameters",
        f"applicationInsightsName={names.application_insights}",
        "--parameters",
        f"logAnalyticsWorkspaceName={names.log_analytics_workspace}",
        "--only-show-errors",
        "--output",
        "json",
    ]


def build_connection_url(
    *,
    subscription_id: str,
    resource_group: str,
    account_name: str,
    project_name: str,
) -> str:
    return (
        "https://management.azure.com"
        f"/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
        f"/projects/{project_name}/connections/{CONNECTION_NAME}"
        f"?api-version={CONNECTION_API_VERSION}"
    )


def build_connection_payload(*, resource_id: str, connection_string: str) -> dict[str, Any]:
    return {
        "properties": {
            "category": "AppInsights",
            "target": resource_id,
            "authType": "ApiKey",
            "isSharedToAll": True,
            "credentials": {"key": connection_string},
            "metadata": {"ApiType": "Azure", "ResourceId": resource_id},
        }
    }


def _resolve_executable(program: str) -> str:
    # Windows ships the Azure CLI as 'az.cmd'; subprocess does not apply PATHEXT.
    return shutil.which(program) or program


def _run_json(args: list[str]) -> Any:
    resolved = [_resolve_executable(args[0]), *args[1:]]
    result = subprocess.run(resolved, check=True, capture_output=True, text=True)
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def _run_raw(args: list[str]) -> str:
    resolved = [_resolve_executable(args[0]), *args[1:]]
    result = subprocess.run(resolved, check=True, capture_output=True, text=True)
    return result.stdout


def _require(name: str, env_values: dict[str, str]) -> str:
    value = resolve_value(name, env_values)
    if not value:
        raise ValueError(f"Missing required environment value: {name}")
    return value


def provision_observability(*, dry_run: bool = False) -> dict[str, Any]:
    env_values = get_values(ignore_errors=True)

    resource_group = _require("AZURE_RESOURCE_GROUP", env_values)
    location = _require("AZURE_LOCATION", env_values)
    account_name = _require("AZURE_AI_ACCOUNT_NAME", env_values)
    project_name = _require("AZURE_AI_PROJECT_NAME", env_values)

    names = build_resource_names(account_name)
    summary: dict[str, Any] = {
        "status": "planned" if dry_run else "success",
        "mode": "dry-run" if dry_run else "apply",
        "resourceGroup": resource_group,
        "location": location,
        "applicationInsightsName": names.application_insights,
        "logAnalyticsWorkspaceName": names.log_analytics_workspace,
        "connectionName": CONNECTION_NAME,
    }

    if dry_run:
        return summary

    subscription_id = _require("AZURE_SUBSCRIPTION_ID", env_values)

    deployment = _run_json(
        build_deployment_args(
            resource_group=resource_group,
            location=location,
            names=names,
        )
    )
    outputs = ((deployment or {}).get("properties") or {}).get("outputs") or {}
    connection_string = (outputs.get("connectionString") or {}).get("value", "")
    resource_id = (outputs.get("resourceId") or {}).get("value", "")
    if not connection_string or not resource_id:
        raise RuntimeError("Application Insights deployment did not return the expected outputs.")

    url = build_connection_url(
        subscription_id=subscription_id,
        resource_group=resource_group,
        account_name=account_name,
        project_name=project_name,
    )
    payload = build_connection_payload(
        resource_id=resource_id,
        connection_string=connection_string,
    )
    _run_raw(
        [
            "az",
            "rest",
            "--method",
            "put",
            "--url",
            url,
            "--body",
            json.dumps(payload),
            "--only-show-errors",
        ]
    )

    set_value(CONNECTION_STRING_ENV_VAR, connection_string)

    summary["applicationInsightsResourceId"] = resource_id
    summary["connectionConfigured"] = True
    summary["environmentVariable"] = CONNECTION_STRING_ENV_VAR
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Provision Application Insights, connect it to the Foundry project, and publish "
            "the connection string to the azd environment."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve names and report the plan without calling Azure.",
    )
    parser.add_argument("--output", help="Optional path to write the JSON summary artifact.")
    args = parser.parse_args()

    summary = provision_observability(dry_run=args.dry_run)
    rendered = json.dumps(summary, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import pytest

from lifecycle_ops.provisioning import observability as target

ENV = {
    "AZURE_RESOURCE_GROUP": "rg-agent-lifecycle-demo",
    "AZURE_LOCATION": "eastus2",
    "AZURE_AI_ACCOUNT_NAME": "cog-b6hrlxpaff37w",
    "AZURE_AI_PROJECT_NAME": "agent-lifecycle-demo",
}


def test_resource_names_derive_from_the_foundry_account_token() -> None:
    # The Foundry account is cog-<token>; reusing the token keeps the observability
    # resources aligned with the rest of the environment.
    names = target.build_resource_names("cog-b6hrlxpaff37w")

    assert names.application_insights == "appi-b6hrlxpaff37w"
    assert names.log_analytics_workspace == "log-b6hrlxpaff37w"


def test_resource_names_reject_an_unexpected_account_name() -> None:
    with pytest.raises(ValueError, match="cog-"):
        target.build_resource_names("some-other-account")


def test_deployment_command_targets_the_observability_module() -> None:
    names = target.build_resource_names("cog-b6hrlxpaff37w")

    args = target.build_deployment_args(
        resource_group="rg-agent-lifecycle-demo",
        location="eastus2",
        names=names,
    )

    assert args[:4] == ["az", "deployment", "group", "create"]
    assert "--resource-group" in args
    assert "rg-agent-lifecycle-demo" in args
    assert "deploy/infra/modules/observability.bicep" in args
    assert "applicationInsightsName=appi-b6hrlxpaff37w" in args
    assert "logAnalyticsWorkspaceName=log-b6hrlxpaff37w" in args
    assert "location=eastus2" in args
    assert "--only-show-errors" in args


def test_connection_payload_makes_traces_visible_in_foundry() -> None:
    payload = target.build_connection_payload(
        resource_id="/subscriptions/s/resourceGroups/rg/providers/microsoft.insights/components/appi",
        connection_string="InstrumentationKey=abc;IngestionEndpoint=https://e.test/",
    )

    assert payload["properties"]["category"] == "AppInsights"
    assert payload["properties"]["authType"] == "ApiKey"
    assert payload["properties"]["isSharedToAll"] is True
    assert payload["properties"]["target"].endswith("/components/appi")
    assert payload["properties"]["credentials"]["key"].startswith("InstrumentationKey=")
    assert payload["properties"]["metadata"]["ApiType"] == "Azure"


def test_connection_url_addresses_the_project_scope() -> None:
    url = target.build_connection_url(
        subscription_id="2cf925b6",
        resource_group="rg-agent-lifecycle-demo",
        account_name="cog-b6hrlxpaff37w",
        project_name="agent-lifecycle-demo",
    )

    assert "/resourceGroups/rg-agent-lifecycle-demo/" in url
    assert "/accounts/cog-b6hrlxpaff37w/projects/agent-lifecycle-demo/connections/" in url
    assert url.endswith("appinsights-connection?api-version=2025-04-01-preview")


def test_provisioning_requires_the_resource_group_and_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(target, "get_values", lambda **_kwargs: {})
    for name in ENV:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError, match="AZURE_RESOURCE_GROUP"):
        target.provision_observability(dry_run=True)


def test_dry_run_reports_the_planned_resources_without_calling_azure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(target, "get_values", lambda **_kwargs: dict(ENV))

    def fail(*_args, **_kwargs):  # pragma: no cover - must not run
        raise AssertionError("dry run must not call Azure")

    monkeypatch.setattr(target, "_run_json", fail)
    monkeypatch.setattr(target, "_run_raw", fail)

    summary = target.provision_observability(dry_run=True)

    assert summary["mode"] == "dry-run"
    assert summary["applicationInsightsName"] == "appi-b6hrlxpaff37w"
    assert summary["logAnalyticsWorkspaceName"] == "log-b6hrlxpaff37w"
    assert summary["connectionName"] == "appinsights-connection"

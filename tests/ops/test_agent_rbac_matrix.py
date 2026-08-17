from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import lifecycle_ops.provisioning.rbac as target
from lifecycle_ops.provisioning.rbac import (
    DEPARTMENT_BY_AGENT,
    ROLE_NAME,
    _get_project_endpoint,
    build_desired_scope_matrix,
    build_role_assignment_create_args,
    build_role_assignment_list_args,
    detect_forbidden_assignments,
)


def _fake_agent(name: str, principal_id: str | None) -> SimpleNamespace:
    """Mirror the SDK shape: identity lives on the latest version, not on the agent."""
    latest = SimpleNamespace(
        instance_identity=SimpleNamespace(principal_id=principal_id) if principal_id else None
    )
    return SimpleNamespace(
        name=name,
        instance_identity=None,
        versions=SimpleNamespace(latest=latest),
    )


def test_get_agent_principal_ids_reads_identity_from_latest_version() -> None:
    agents = [
        _fake_agent("development-agent", "p-dev"),
        _fake_agent("human-resources-agent", "p-hr"),
        _fake_agent("marketing-agent", "p-mkt"),
    ]

    assert target._extract_principal_ids(agents) == {
        "development-agent": "p-dev",
        "human-resources-agent": "p-hr",
        "marketing-agent": "p-mkt",
    }


def test_get_agent_principal_ids_still_raises_when_identity_absent() -> None:
    agents = [
        _fake_agent("development-agent", "p-dev"),
        _fake_agent("human-resources-agent", None),
        _fake_agent("marketing-agent", "p-mkt"),
    ]

    with pytest.raises(RuntimeError, match="human-resources-agent"):
        target._extract_principal_ids(agents)


def test_run_json_command_resolves_executable_via_pathext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # On Windows the Azure CLI is 'az.cmd'; subprocess does not apply PATHEXT, so the
    # program has to be resolved before spawning or the hook dies with WinError 2.
    monkeypatch.setattr(
        target.shutil,
        "which",
        lambda program: r"C:\tools\az.cmd" if program == "az" else None,
    )
    captured: dict[str, list[str]] = {}

    def fake_run(args, **_kwargs):
        captured["args"] = args
        return SimpleNamespace(stdout="[]")

    monkeypatch.setattr(target.subprocess, "run", fake_run)

    assert target._run_json_command(["az", "role", "assignment", "list"]) == []
    assert captured["args"] == [r"C:\tools\az.cmd", "role", "assignment", "list"]


def _mapping_style_agent(name: str, principal_id: str) -> SimpleNamespace:
    """Older SDK builds expose nested version fields only as mapping keys."""
    latest = {"instance_identity": {"principal_id": principal_id}}
    return SimpleNamespace(name=name, versions={"latest": latest})


def test_get_agent_principal_ids_supports_mapping_style_sdk_models() -> None:
    agents = [
        _mapping_style_agent("development-agent", "p-dev"),
        _mapping_style_agent("human-resources-agent", "p-hr"),
        _mapping_style_agent("marketing-agent", "p-mkt"),
    ]

    assert target._extract_principal_ids(agents) == {
        "development-agent": "p-dev",
        "human-resources-agent": "p-hr",
        "marketing-agent": "p-mkt",
    }


def test_desired_scope_matrix_grants_shared_plus_own_only() -> None:
    principal_ids = {
        "development-agent": "11111111-1111-1111-1111-111111111111",
        "human-resources-agent": "22222222-2222-2222-2222-222222222222",
        "marketing-agent": "33333333-3333-3333-3333-333333333333",
    }
    resource_ids = {
        "shared": "/subs/s1/rg/rg1/providers/Microsoft.Search/searchServices/shared",
        "development": "/subs/s1/rg/rg1/providers/Microsoft.Search/searchServices/dev",
        "human-resources": "/subs/s1/rg/rg1/providers/Microsoft.Search/searchServices/hr",
        "marketing": "/subs/s1/rg/rg1/providers/Microsoft.Search/searchServices/mkt",
    }

    matrix = build_desired_scope_matrix(principal_ids=principal_ids, resource_ids=resource_ids)

    for agent_name, department in DEPARTMENT_BY_AGENT.items():
        assert matrix[agent_name]["department"] == department
        assert matrix[agent_name]["allowedScopes"] == [
            resource_ids["shared"],
            resource_ids[department],
        ]


def test_detect_forbidden_assignments_flags_cross_department_scope() -> None:
    matrix = {
        "development-agent": {
            "department": "development",
            "principalId": "11111111-1111-1111-1111-111111111111",
            "allowedScopes": [
                "/subs/s1/rg/rg1/providers/Microsoft.Search/searchServices/shared",
                "/subs/s1/rg/rg1/providers/Microsoft.Search/searchServices/dev",
            ],
        }
    }

    existing_assignments = {
        "development-agent": [
            {
                "scope": "/subs/s1/rg/rg1/providers/Microsoft.Search/searchServices/shared",
                "roleDefinitionName": "Search Index Data Reader",
            },
            {
                "scope": "/subs/s1/rg/rg1/providers/Microsoft.Search/searchServices/hr",
                "roleDefinitionName": "Search Index Data Reader",
            },
        ]
    }

    forbidden = detect_forbidden_assignments(
        desired_matrix=matrix,
        existing_assignments=existing_assignments,
    )

    assert len(forbidden) == 1
    assert forbidden[0]["agentName"] == "development-agent"
    assert forbidden[0]["scope"].endswith("/hr")


def test_role_assignment_command_builders_include_required_flags() -> None:
    list_args = build_role_assignment_list_args(
        principal_id="11111111-1111-1111-1111-111111111111",
        scope="/subs/s1/rg/rg1/providers/Microsoft.Search/searchServices/shared",
        role_name=ROLE_NAME,
    )
    create_args = build_role_assignment_create_args(
        principal_id="11111111-1111-1111-1111-111111111111",
        scope="/subs/s1/rg/rg1/providers/Microsoft.Search/searchServices/shared",
        role_id_or_name="abcd1234-0000-0000-0000-000000000000",
    )

    assert list_args[:4] == ["az", "role", "assignment", "list"]
    assert "--assignee-object-id" in list_args
    assert "--scope" in list_args
    assert "--role" in list_args

    assert create_args[:4] == ["az", "role", "assignment", "create"]
    assert "--assignee-object-id" in create_args
    assert "--scope" in create_args
    assert "--role" in create_args


def test_get_project_endpoint_prefers_azure_alias(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_AI_PROJECT_ENDPOINT", "https://azure-alias.example")
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://foundry.example")

    value = _get_project_endpoint({})
    assert value == "https://azure-alias.example"


def test_get_project_endpoint_falls_back_to_foundry_alias(monkeypatch) -> None:
    monkeypatch.delenv("AZURE_AI_PROJECT_ENDPOINT", raising=False)
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://foundry.example")

    value = _get_project_endpoint({})
    assert value == "https://foundry.example"


def test_get_project_endpoint_reads_from_azd_env_aliases(monkeypatch) -> None:
    monkeypatch.delenv("AZURE_AI_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)

    value = _get_project_endpoint(
        {
            "FOUNDRY_PROJECT_ENDPOINT": "https://from-azd-foundry.example",
            "AZURE_AI_PROJECT_ENDPOINT": "https://from-azd-azure.example",
        }
    )
    assert value == "https://from-azd-azure.example"


def test_get_project_endpoint_missing_raises(monkeypatch) -> None:
    monkeypatch.delenv("AZURE_AI_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)

    try:
        _get_project_endpoint({})
    except ValueError as exc:
        assert "AZURE_AI_PROJECT_ENDPOINT" in str(exc)
    else:
        raise AssertionError("Expected ValueError when endpoint aliases are missing")


def test_apply_search_rbac_reports_planned_and_final_missing_after_recollect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(target, "_load_active_azd_environment", lambda: {})
    monkeypatch.setattr(target, "_get_project_endpoint", lambda _env: "https://example")
    monkeypatch.setattr(
        target,
        "_get_search_resource_ids",
        lambda _env: {
            "shared": "/s/shared",
            "development": "/s/dev",
            "human-resources": "/s/hr",
            "marketing": "/s/mkt",
        },
    )
    monkeypatch.setattr(
        target,
        "get_agent_principal_ids",
        lambda _endpoint: {
            "development-agent": "p-dev",
            "human-resources-agent": "p-hr",
            "marketing-agent": "p-mkt",
        },
    )
    monkeypatch.setattr(target, "resolve_role_definition_id", lambda _name: "role-guid")

    collect_calls = {"count": 0}

    def fake_collect_existing_assignments(*, desired_matrix, all_known_scopes):
        collect_calls["count"] += 1
        if collect_calls["count"] == 1:
            return {agent_name: [] for agent_name in desired_matrix}
        return {
            "development-agent": [
                {"scope": "/s/shared", "roleDefinitionName": ROLE_NAME},
                {"scope": "/s/dev", "roleDefinitionName": ROLE_NAME},
            ],
            "human-resources-agent": [
                {"scope": "/s/shared", "roleDefinitionName": ROLE_NAME},
                {"scope": "/s/hr", "roleDefinitionName": ROLE_NAME},
            ],
            "marketing-agent": [
                {"scope": "/s/shared", "roleDefinitionName": ROLE_NAME},
            ],
        }

    monkeypatch.setattr(target, "_collect_existing_assignments", fake_collect_existing_assignments)
    monkeypatch.setattr(target, "_run_json_command", lambda _args: {"created": True})

    report = target.apply_search_rbac(dry_run=False)

    assert report["dryRun"] is False
    assert len(report["plannedAssignments"]) == 6
    assert report["missingAssignments"] == [
        {
            "agentName": "marketing-agent",
            "principalId": "p-mkt",
            "scope": "/s/mkt",
        }
    ]


def test_apply_search_rbac_dry_run_keeps_final_missing_equal_to_planned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(target, "_load_active_azd_environment", lambda: {})
    monkeypatch.setattr(target, "_get_project_endpoint", lambda _env: "https://example")
    monkeypatch.setattr(
        target,
        "_get_search_resource_ids",
        lambda _env: {
            "shared": "/s/shared",
            "development": "/s/dev",
            "human-resources": "/s/hr",
            "marketing": "/s/mkt",
        },
    )
    monkeypatch.setattr(
        target,
        "get_agent_principal_ids",
        lambda _endpoint: {
            "development-agent": "p-dev",
            "human-resources-agent": "p-hr",
            "marketing-agent": "p-mkt",
        },
    )
    monkeypatch.setattr(target, "resolve_role_definition_id", lambda _name: "role-guid")
    monkeypatch.setattr(
        target,
        "_collect_existing_assignments",
        lambda *, desired_matrix, all_known_scopes: {
            agent_name: [] for agent_name in desired_matrix
        },
    )

    report = target.apply_search_rbac(dry_run=True)

    assert report["dryRun"] is True
    assert report["missingAssignments"] == report["plannedAssignments"]
    assert len(report["missingAssignments"]) == 6


def test_main_prints_json_writes_report_and_returns_two_when_missing_non_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report_path = tmp_path / "rbac.json"
    monkeypatch.setattr(
        target.argparse.ArgumentParser,
        "parse_args",
        lambda self: SimpleNamespace(dry_run=False, report_path=str(report_path)),
    )
    monkeypatch.setattr(
        target,
        "apply_search_rbac",
        lambda *, dry_run: {
            "dryRun": False,
            "plannedAssignments": [{"agentName": "marketing-agent"}],
            "missingAssignments": [{"agentName": "marketing-agent"}],
            "forbiddenAssignments": [],
        },
    )

    exit_code = target.main()
    captured = capsys.readouterr().out

    assert exit_code == 2
    assert json.loads(captured)["missingAssignments"]
    assert json.loads(report_path.read_text(encoding="utf-8"))["missingAssignments"]

from __future__ import annotations

from scripts.set_agent_rbac import (
    DEPARTMENT_BY_AGENT,
    ROLE_NAME,
    _get_project_endpoint,
    build_desired_scope_matrix,
    build_role_assignment_create_args,
    build_role_assignment_list_args,
    detect_forbidden_assignments,
)


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

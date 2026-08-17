from __future__ import annotations

import re
from pathlib import Path

import yaml


def _infra_path(*parts: str) -> Path:
    return Path(__file__).resolve().parents[2].joinpath("deploy", "infra", *parts)


def _extract_search_services_keys(bicepparam_text: str) -> list[str]:
    marker = "param searchServices = {"
    start = bicepparam_text.find(marker)
    if start == -1:
        raise AssertionError("searchServices object parameter was not found")

    pos = start + len(marker)
    depth = 1
    body_chars: list[str] = []
    while pos < len(bicepparam_text) and depth > 0:
        char = bicepparam_text[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                break
        if depth > 0:
            body_chars.append(char)
        pos += 1

    if depth != 0:
        raise AssertionError("searchServices object parameter is not closed")

    body = "".join(body_chars)
    return re.findall(r"^\s{2}([A-Za-z][A-Za-z0-9]*)\s*:\s*\{", body, flags=re.MULTILINE)


def test_named_search_endpoint_outputs_do_not_use_numeric_module_index() -> None:
    main_bicep = _infra_path("main.bicep").read_text(encoding="utf-8")
    index_ref_pattern = r"output\s+FOUNDRYIQ_SEARCH_ENDPOINT_[A-Z_]+\s+string\s*=\s*.*\[[0-9]+\]"
    assert re.search(index_ref_pattern, main_bicep) is None


def test_main_bicepparam_uses_exactly_four_keyed_search_boundaries() -> None:
    main_bicepparam = _infra_path("main.bicepparam").read_text(encoding="utf-8")
    keys = _extract_search_services_keys(main_bicepparam)
    assert keys == ["shared", "development", "humanResources", "marketing"]


def test_azure_yaml_uses_bicep_provider_for_custom_infrastructure() -> None:
    azure_yaml = Path(__file__).resolve().parents[2] / "azure.yaml"
    config = yaml.safe_load(azure_yaml.read_text(encoding="utf-8"))

    assert config["infra"] == {
        "provider": "bicep",
        "path": "deploy/infra",
    }


def test_main_bicepparam_reads_azd_environment_context() -> None:
    main_bicepparam = _infra_path("main.bicepparam").read_text(encoding="utf-8")

    for declaration in (
        "param location = readEnvironmentVariable('AZURE_LOCATION', 'eastus2')",
        (
            "param resourceGroupName = "
            "readEnvironmentVariable('AZURE_RESOURCE_GROUP', 'provider-managed-rg')"
        ),
        (
            "param foundryProjectName = "
            "readEnvironmentVariable('AZURE_AI_PROJECT_NAME', 'provider-managed')"
        ),
        "param principalId = readEnvironmentVariable('AZURE_PRINCIPAL_ID', '')",
        "param principalType = readEnvironmentVariable('AZURE_PRINCIPAL_TYPE', 'User')",
    ):
        assert declaration in main_bicepparam


def test_search_services_support_a_separate_azd_region() -> None:
    main_bicep = _infra_path("main.bicep").read_text(encoding="utf-8")
    main_bicepparam = _infra_path("main.bicepparam").read_text(encoding="utf-8")

    assert "param searchLocation string = location" in main_bicep
    assert main_bicep.count("location: searchLocation") == 4
    assert (
        "param searchLocation = readEnvironmentVariable('AZURE_SEARCH_LOCATION', 'centralus')"
    ) in main_bicepparam


def test_search_service_names_are_unique_per_deployment_environment() -> None:
    main_bicep = _infra_path("main.bicep").read_text(encoding="utf-8")
    main_bicepparam = _infra_path("main.bicepparam").read_text(encoding="utf-8")

    assert (
        "var searchNameSuffix = uniqueString(subscription().id, resourceGroupName, searchLocation)"
    ) in main_bicep
    assert main_bicep.count("-${searchNameSuffix}'") == 4
    assert "-817" not in main_bicepparam


def test_main_bicep_accepts_foundry_provider_parameters() -> None:
    main_bicep = _infra_path("main.bicep").read_text(encoding="utf-8")
    expected_declarations = {
        "param resourceGroupName string = 'provider-managed-rg'",
        "param resourceTokenSalt string = ''",
        "param foundryProjectName string = 'provider-managed'",
        "param principalId string = ''",
    }

    for declaration in expected_declarations:
        assert declaration in main_bicep


def test_main_bicep_uses_foundry_provider_subscription_scope() -> None:
    main_bicep = _infra_path("main.bicep").read_text(encoding="utf-8")

    assert "targetScope = 'subscription'" in main_bicep
    assert "resource resourceGroup 'Microsoft.Resources/resourceGroups@2021-04-01'" in main_bicep
    assert main_bicep.count("scope: resourceGroup") == 5


def test_main_bicep_provisions_foundry_project_and_model_resources() -> None:
    main_bicep = _infra_path("main.bicep").read_text(encoding="utf-8")
    resources_module = _infra_path("modules", "resources.bicep")

    assert resources_module.exists()
    assert "module resources 'modules/resources.bicep'" in main_bicep
    assert "output FOUNDRY_PROJECT_ENDPOINT string" in main_bicep

    resources_bicep = resources_module.read_text(encoding="utf-8")
    assert "Microsoft.CognitiveServices/accounts@" in resources_bicep
    assert "resource modelDeployments 'deployments'" in resources_bicep
    assert "resource project 'projects'" in resources_bicep


def test_search_services_grant_provisioner_required_data_plane_roles() -> None:
    main_bicep = _infra_path("main.bicep").read_text(encoding="utf-8")
    search_bicep = _infra_path("modules", "search.bicep").read_text(encoding="utf-8")

    assert main_bicep.count("provisionerPrincipalId: principalId") == 4
    assert main_bicep.count("provisionerPrincipalType: principalType") == 4
    assert "7ca78c08-252a-4471-8644-bb5ff32d4ba0" in search_bicep
    assert "8ebe5a00-799e-43f5-93ac-243d3dce84a7" in search_bicep
    assert search_bicep.count("Microsoft.Authorization/roleAssignments@2022-04-01") == 2
    assert search_bicep.count("scope: searchService") == 2


def test_container_registry_is_disabled_for_direct_code_deployment() -> None:
    main_bicep = _infra_path("main.bicep").read_text(encoding="utf-8")

    assert "@allowed([false])\nparam includeAcr bool = false" in main_bicep


def test_ci_compiles_main_bicepparam() -> None:
    ci_workflow = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    assert "az bicep build-params --file deploy/infra/main.bicepparam --stdout" in ci_workflow


def test_main_bicepparam_pins_foundry_model_deployment() -> None:
    main_bicepparam = _infra_path("main.bicepparam").read_text(encoding="utf-8")

    assert "name: 'gpt-5.4-mini'" in main_bicepparam
    assert "version: '2026-03-17'" in main_bicepparam
    assert "name: 'GlobalStandard'" in main_bicepparam
    assert "capacity: 10" in main_bicepparam


def test_every_agent_receives_the_application_insights_connection_string() -> None:
    import yaml

    repository_root = Path(__file__).resolve().parents[2]
    azure_yaml = yaml.safe_load(repository_root.joinpath("azure.yaml").read_text(encoding="utf-8"))

    agents = [
        name
        for name, service in azure_yaml["services"].items()
        if service.get("host") == "azure.ai.agent"
    ]
    assert len(agents) == 3

    for name in agents:
        variables = {
            item["name"]: item["value"]
            for item in azure_yaml["services"][name]["environmentVariables"]
        }
        assert variables["APPLICATIONINSIGHTS_CONNECTION_STRING"] == (
            "${APPLICATIONINSIGHTS_CONNECTION_STRING}"
        )


def test_observability_module_declares_application_insights_and_workspace() -> None:
    """Deployed by the postprovision hook, not by `azd provision`.

    The microsoft.foundry provider synthesises its own ARM template containing only
    the Foundry account, project and model deployment, so resources declared in
    main.bicep never reach ARM.
    """
    module = _infra_path("modules", "observability.bicep")
    assert module.exists()

    source = module.read_text(encoding="utf-8")
    assert "Microsoft.OperationalInsights/workspaces@" in source
    assert "Microsoft.Insights/components@" in source
    assert "WorkspaceResourceId: logAnalyticsWorkspace.id" in source
    assert "output connectionString string" in source
    assert "output resourceId string" in source


def test_observability_module_is_not_wired_into_the_unused_provider_template() -> None:
    main_bicep = _infra_path("main.bicep").read_text(encoding="utf-8")

    assert "modules/observability.bicep" not in main_bicep


def test_project_identity_is_granted_foundry_user_for_continuous_evaluation() -> None:
    """The Operate stage cannot register evaluation rules without this role.

    Foundry rejects `evaluation_rules.create_or_update` with "Project managed identity
    lacks Foundry User role on the project".
    """
    resources_bicep = _infra_path("modules", "resources.bicep").read_text(encoding="utf-8")

    # Foundry User
    assert "53ca6127-db72-4b80-b1b0-d745d6d5456d" in resources_bicep
    assert "foundryAccount::project.identity.principalId" in resources_bicep

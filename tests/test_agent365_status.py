from __future__ import annotations

from types import SimpleNamespace

import pytest

import lifecycle_ops.operations.agent365.readiness as configure_observability_module
import lifecycle_ops.operations.agent365.registry as verify_registry_module
from lifecycle_ops.operations.agent365.readiness import (
    evaluate_agent365_observability_readiness,
)
from lifecycle_ops.operations.agent365.registry import (
    AGENT_NAMES,
    verify_agent365_registry_status,
)


class _PackageInspector:
    def __init__(self, available: set[str]) -> None:
        self.available = available

    def is_importable(self, package_name: str) -> bool:
        return package_name in self.available

    def has_distribution(self, package_name: str) -> bool:
        return package_name in self.available


class _FakeGraphClient:
    def __init__(
        self,
        *,
        service_principal_exists: bool,
        role_exists: bool,
        assignment_exists_by_principal: dict[str, bool],
        permission_error_on_sp_lookup: bool = False,
    ) -> None:
        self.service_principal_exists = service_principal_exists
        self.role_exists = role_exists
        self.assignment_exists_by_principal = assignment_exists_by_principal
        self.permission_error_on_sp_lookup = permission_error_on_sp_lookup

    def find_service_principal(self, display_name: str):
        if self.permission_error_on_sp_lookup:
            raise PermissionError("insufficient directory permissions")
        if not self.service_principal_exists:
            return None
        return {"id": "sp-123", "displayName": display_name}

    def find_app_role(self, service_principal_id: str, role_value: str):
        if not self.role_exists:
            return None
        return {"id": "role-123", "value": role_value, "servicePrincipalId": service_principal_id}

    def has_app_role_assignment(
        self,
        *,
        principal_object_id: str,
        resource_service_principal_id: str,
        app_role_id: str,
    ) -> bool:
        return self.assignment_exists_by_principal.get(principal_object_id, False)


def _all_agent_principal_ids() -> dict[str, str]:
    return {
        "development-agent": "dev-obj",
        "human-resources-agent": "hr-obj",
        "marketing-agent": "mkt-obj",
    }


def test_agent365_observability_readiness_skips_when_packages_missing() -> None:
    package_index = _PackageInspector(available={"azure-monitor-opentelemetry"})

    status = evaluate_agent365_observability_readiness(package_index=package_index)

    assert status["status"] == "prerequisite-skipped"
    assert "app insights" in status["reason"].lower() or "package" in status["reason"].lower()
    assert status["runtime_observability"] == "app-insights"


def test_agent365_observability_readiness_defaults_to_sensitive_input_suppression() -> None:
    package_index = _PackageInspector(
        available={
            "microsoft-opentelemetry",
        }
    )

    status = evaluate_agent365_observability_readiness(
        package_index=package_index,
        env={"ENABLE_A365_OBSERVABILITY_EXPORTER": "false"},
    )

    assert status["status"] == "prerequisite-skipped"
    assert status["settings"]["a365_suppress_invoke_agent_input"] is True


def test_agent365_observability_readiness_requires_explicit_enable_and_packages() -> None:
    package_index = _PackageInspector(
        available={
            "microsoft-agents-a365-observability-extensions-agent-framework",
            "microsoft-agents-a365-observability-core",
            "microsoft-agents-a365-runtime",
            "microsoft.opentelemetry.a365.extensions.agent_framework",
            "microsoft.opentelemetry.a365.core",
            "microsoft.opentelemetry.a365",
        }
    )

    status = evaluate_agent365_observability_readiness(
        package_index=package_index,
        env={"ENABLE_A365_OBSERVABILITY_EXPORTER": "true"},
    )

    assert status["status"] == "verified"
    assert status["settings"]["a365_suppress_invoke_agent_input"] is True


def test_verify_agent365_registry_reports_verified_when_assignment_present() -> None:
    graph_client = _FakeGraphClient(
        service_principal_exists=True,
        role_exists=True,
        assignment_exists_by_principal={
            "dev-obj": True,
            "hr-obj": True,
            "mkt-obj": True,
        },
    )

    status = verify_agent365_registry_status(
        graph_client=graph_client,
        hosted_agent_object_ids_by_name=_all_agent_principal_ids(),
    )

    assert status["status"] == "verified"


def test_verify_agent365_registry_reports_prerequisite_skipped_when_sp_missing() -> None:
    graph_client = _FakeGraphClient(
        service_principal_exists=False,
        role_exists=False,
        assignment_exists_by_principal={},
    )

    status = verify_agent365_registry_status(
        graph_client=graph_client,
        hosted_agent_object_ids_by_name=_all_agent_principal_ids(),
    )

    assert status["status"] == "prerequisite-skipped"
    assert "agent365observability" in status["reason"].lower()


def test_verify_agent365_registry_fails_on_partial_drift() -> None:
    graph_client = _FakeGraphClient(
        service_principal_exists=True,
        role_exists=True,
        assignment_exists_by_principal={
            "dev-obj": True,
            "hr-obj": False,
            "mkt-obj": True,
        },
    )

    status = verify_agent365_registry_status(
        graph_client=graph_client,
        hosted_agent_object_ids_by_name=_all_agent_principal_ids(),
        prerequisites_claimed=True,
    )

    assert status["status"] == "failed"
    assert "assignment" in status["reason"].lower()


def test_verify_agent365_registry_returns_skipped_when_any_agent_prereq_skipped_but_none_failed(
) -> None:
    graph_client = _FakeGraphClient(
        service_principal_exists=True,
        role_exists=True,
        assignment_exists_by_principal={
            "dev-obj": True,
            "hr-obj": False,
            "mkt-obj": True,
        },
    )

    status = verify_agent365_registry_status(
        graph_client=graph_client,
        hosted_agent_object_ids_by_name=_all_agent_principal_ids(),
        prerequisites_claimed=False,
    )

    assert status["status"] == "prerequisite-skipped"


def test_verify_agent365_registry_handles_permission_error_contract() -> None:
    graph_client = _FakeGraphClient(
        service_principal_exists=False,
        role_exists=False,
        assignment_exists_by_principal={},
        permission_error_on_sp_lookup=True,
    )

    skipped = verify_agent365_registry_status(
        graph_client=graph_client,
        hosted_agent_object_ids_by_name=_all_agent_principal_ids(),
        prerequisites_claimed=False,
    )
    failed = verify_agent365_registry_status(
        graph_client=graph_client,
        hosted_agent_object_ids_by_name=_all_agent_principal_ids(),
        prerequisites_claimed=True,
    )

    assert skipped["status"] == "prerequisite-skipped"
    assert failed["status"] == "failed"


def test_verify_agent365_registry_supports_focused_single_agent_ids() -> None:
    graph_client = _FakeGraphClient(
        service_principal_exists=True,
        role_exists=True,
        assignment_exists_by_principal={"dev-obj": True},
    )

    status = verify_agent365_registry_status(
        graph_client=graph_client,
        hosted_agent_object_ids_by_name={"development-agent": "dev-obj"},
    )

    assert status["status"] == "verified"


def test_registry_main_exit_code_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        verify_registry_module,
        "_resolve_hosted_agent_object_ids",
        lambda project_endpoint, explicit_object_ids=None: _all_agent_principal_ids(),
    )
    monkeypatch.setattr(
        verify_registry_module,
        "verify_agent365_registry_status",
        lambda **_: {"status": "failed", "reason": "boom"},
    )
    monkeypatch.setattr(
        verify_registry_module.argparse.ArgumentParser,
        "parse_args",
        lambda self: SimpleNamespace(
            hosted_agent_object_id=None,
            development_agent_object_id=None,
            human_resources_agent_object_id=None,
            marketing_agent_object_id=None,
            foundry_project_endpoint="https://example.foundry.azure.com",
            prerequisites_claimed=True,
            grant=False,
        ),
    )

    assert verify_registry_module.main() == 2


def test_observability_main_exit_code_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        configure_observability_module,
        "evaluate_agent365_observability_readiness",
        lambda **_: {"status": "verified", "reason": "ok"},
    )
    assert configure_observability_module.main() == 0

    monkeypatch.setattr(
        configure_observability_module,
        "evaluate_agent365_observability_readiness",
        lambda **_: {"status": "failed", "reason": "broken"},
    )
    assert configure_observability_module.main() == 2


def test_registry_agent_names_default_contains_three_expected_agents() -> None:
    assert AGENT_NAMES == [
        "development-agent",
        "human-resources-agent",
        "marketing-agent",
    ]

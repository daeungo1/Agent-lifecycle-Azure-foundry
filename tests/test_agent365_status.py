from __future__ import annotations

from scripts.agent365.configure_observability import evaluate_agent365_observability_readiness
from scripts.agent365.verify_registry import verify_agent365_registry_status


class _PackageIndex:
    def __init__(self, available: set[str]) -> None:
        self.available = available

    def has_package(self, package_name: str) -> bool:
        return package_name in self.available


class _FakeGraphClient:
    def __init__(
        self,
        *,
        service_principal_exists: bool,
        role_exists: bool,
        assignment_exists: bool,
    ) -> None:
        self.service_principal_exists = service_principal_exists
        self.role_exists = role_exists
        self.assignment_exists = assignment_exists

    def find_service_principal(self, display_name: str):
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
        return self.assignment_exists


def test_agent365_observability_readiness_skips_when_packages_missing() -> None:
    package_index = _PackageIndex(available={"azure-monitor-opentelemetry"})

    status = evaluate_agent365_observability_readiness(package_index=package_index)

    assert status["status"] == "prerequisite-skipped"
    assert "package" in status["reason"].lower()
    assert status["runtime_observability"] == "app-insights"


def test_agent365_observability_readiness_defaults_to_sensitive_input_suppression() -> None:
    package_index = _PackageIndex(
        available={
            "microsoft-opentelemetry",
        }
    )

    status = evaluate_agent365_observability_readiness(package_index=package_index)

    assert status["status"] == "verified"
    assert status["settings"]["a365_suppress_invoke_agent_input"] is True


def test_verify_agent365_registry_reports_verified_when_assignment_present() -> None:
    graph_client = _FakeGraphClient(
        service_principal_exists=True,
        role_exists=True,
        assignment_exists=True,
    )

    status = verify_agent365_registry_status(
        graph_client=graph_client,
        hosted_agent_object_id="agent-obj-1",
    )

    assert status["status"] == "verified"


def test_verify_agent365_registry_reports_prerequisite_skipped_when_sp_missing() -> None:
    graph_client = _FakeGraphClient(
        service_principal_exists=False,
        role_exists=False,
        assignment_exists=False,
    )

    status = verify_agent365_registry_status(
        graph_client=graph_client,
        hosted_agent_object_id="agent-obj-1",
    )

    assert status["status"] == "prerequisite-skipped"
    assert "agent365observability" in status["reason"].lower()


def test_verify_agent365_registry_fails_on_partial_drift() -> None:
    graph_client = _FakeGraphClient(
        service_principal_exists=True,
        role_exists=True,
        assignment_exists=False,
    )

    status = verify_agent365_registry_status(
        graph_client=graph_client,
        hosted_agent_object_id="agent-obj-1",
        prerequisites_claimed=True,
    )

    assert status["status"] == "failed"
    assert "assignment" in status["reason"].lower()

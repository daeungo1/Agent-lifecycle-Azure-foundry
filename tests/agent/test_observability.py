import logging
import os

import pytest

from lifecycle_agent.observability import configure_observability


def test_configure_observability_defaults_to_safe_console_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_use_microsoft_opentelemetry(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.delenv("ENABLE_A365_OBSERVABILITY_EXPORTER", raising=False)
    monkeypatch.setattr(
        "lifecycle_agent.observability._load_microsoft_observability_entrypoint",
        lambda: fake_use_microsoft_opentelemetry,
    )

    configure_observability("development")

    assert captured["enable_sensitive_data"] is False
    assert captured["enable_a365"] is False
    assert captured["a365_enable_observability_exporter"] is False
    assert captured["a365_suppress_invoke_agent_input"] is True
    assert captured["enable_console"] is True


def test_configure_observability_enables_a365_only_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_use_microsoft_opentelemetry(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setenv("ENABLE_A365_OBSERVABILITY_EXPORTER", "true")
    monkeypatch.setattr(
        "lifecycle_agent.observability._load_microsoft_observability_entrypoint",
        lambda: fake_use_microsoft_opentelemetry,
    )

    configure_observability("marketing")

    assert captured["enable_a365"] is True
    assert captured["a365_enable_observability_exporter"] is True
    assert captured["enable_console"] is False
    assert captured["a365_suppress_invoke_agent_input"] is True


def test_configure_observability_handles_missing_optional_dependency(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("ENABLE_A365_OBSERVABILITY_EXPORTER", "true")
    monkeypatch.setattr(
        "lifecycle_agent.observability._load_microsoft_observability_entrypoint",
        lambda: None,
    )

    with caplog.at_level(logging.WARNING):
        configure_observability("human-resources")

    assert "disabled" in caplog.text.lower()
    assert "microsoft-opentelemetry" in caplog.text


def test_configure_observability_exports_to_application_insights_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Foundry renders agent traces from the connected Application Insights resource,
    # so the runtime has to export spans there rather than only to the console.
    captured: dict[str, object] = {}

    def fake_use_microsoft_opentelemetry(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.delenv("ENABLE_A365_OBSERVABILITY_EXPORTER", raising=False)
    monkeypatch.setenv(
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "InstrumentationKey=00000000-0000-0000-0000-000000000000;IngestionEndpoint=https://e.test/",
    )
    monkeypatch.setattr(
        "lifecycle_agent.observability._load_microsoft_observability_entrypoint",
        lambda: fake_use_microsoft_opentelemetry,
    )

    configure_observability("development")

    assert captured["enable_azure_monitor"] is True
    assert captured["azure_monitor_connection_string"].startswith("InstrumentationKey=")
    assert captured["enable_sensitive_data"] is False


def test_configure_observability_skips_azure_monitor_without_a_connection_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_use_microsoft_opentelemetry(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.delenv("ENABLE_A365_OBSERVABILITY_EXPORTER", raising=False)
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    monkeypatch.setattr(
        "lifecycle_agent.observability._load_microsoft_observability_entrypoint",
        lambda: fake_use_microsoft_opentelemetry,
    )

    configure_observability("marketing")

    assert captured["enable_azure_monitor"] is False
    assert "azure_monitor_connection_string" not in captured


def test_configure_observability_names_the_service_per_department(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Without a service name every span lands under cloud_RoleName "unknown_service",
    # so Foundry and App Insights cannot attribute traces to a department agent.
    def fake_use_microsoft_opentelemetry(**kwargs) -> None:
        return None

    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("ENABLE_A365_OBSERVABILITY_EXPORTER", raising=False)
    monkeypatch.setattr(
        "lifecycle_agent.observability._load_microsoft_observability_entrypoint",
        lambda: fake_use_microsoft_opentelemetry,
    )

    configure_observability("human-resources")

    assert os.environ["OTEL_SERVICE_NAME"] == "human-resources-agent"


def test_configure_observability_keeps_an_explicit_service_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_use_microsoft_opentelemetry(**kwargs) -> None:
        return None

    monkeypatch.setenv("OTEL_SERVICE_NAME", "operator-chosen-name")
    monkeypatch.setattr(
        "lifecycle_agent.observability._load_microsoft_observability_entrypoint",
        lambda: fake_use_microsoft_opentelemetry,
    )

    configure_observability("marketing")

    assert os.environ["OTEL_SERVICE_NAME"] == "operator-chosen-name"

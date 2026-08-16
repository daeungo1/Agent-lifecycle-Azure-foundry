import logging

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

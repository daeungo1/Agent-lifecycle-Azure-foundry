from __future__ import annotations

import importlib
import importlib.metadata
import json
from dataclasses import dataclass
from typing import Any

A365_REQUIRED_COMPONENTS = [
    {
        "distribution": "microsoft-agents-a365-observability-extensions-agent-framework",
        "module": "microsoft.opentelemetry.a365.extensions.agent_framework",
    },
    {
        "distribution": "microsoft-agents-a365-observability-core",
        "module": "microsoft.opentelemetry.a365.core",
    },
    {
        "distribution": "microsoft-agents-a365-runtime",
        "module": "microsoft.opentelemetry.a365",
    },
]
ENABLE_EXPORTER_ENV = "ENABLE_A365_OBSERVABILITY_EXPORTER"


@dataclass
class LocalPackageInspector:
    def has_distribution(self, package_name: str) -> bool:
        try:
            importlib.metadata.version(package_name)
            return True
        except importlib.metadata.PackageNotFoundError:
            return False

    def is_importable(self, package_name: str) -> bool:
        try:
            importlib.import_module(package_name)
            return True
        except ModuleNotFoundError:
            return False


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _status(
    *,
    status: str,
    reason: str,
    runtime_observability: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "runtime_observability": runtime_observability,
        "settings": settings,
    }


def evaluate_agent365_observability_readiness(
    *,
    package_index: Any | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    package_index = package_index or LocalPackageInspector()
    env = env or {}

    safe_defaults = {
        "a365_suppress_invoke_agent_input": True,
    }
    enabled = _is_truthy(env.get(ENABLE_EXPORTER_ENV))

    missing_distributions: list[str] = []
    missing_modules: list[str] = []
    for component in A365_REQUIRED_COMPONENTS:
        distribution = str(component["distribution"])
        module_name = str(component["module"])
        if not package_index.has_distribution(distribution):
            missing_distributions.append(distribution)
        if not package_index.is_importable(module_name):
            missing_modules.append(module_name)

    if enabled and (missing_distributions or missing_modules):
        return _status(
            status="failed",
            reason=(
                "ENABLE_A365_OBSERVABILITY_EXPORTER=true but required Agent365 components "
                "are missing or not importable. Missing distributions: "
                + (", ".join(missing_distributions) if missing_distributions else "none")
                + "; missing modules: "
                + (", ".join(missing_modules) if missing_modules else "none")
            ),
            runtime_observability="app-insights-fallback",
            settings=safe_defaults,
        )

    if not enabled:
        return _status(
            status="prerequisite-skipped",
            reason=(
                "ENABLE_A365_OBSERVABILITY_EXPORTER is not set to true. "
                "Using App Insights-compatible fallback configuration."
            ),
            runtime_observability="app-insights",
            settings=safe_defaults,
        )

    if missing_distributions or missing_modules:
        return _status(
            status="prerequisite-skipped",
            reason=(
                "Agent365 observability prerequisites are not fully available in this environment."
            ),
            runtime_observability="app-insights",
            settings=safe_defaults,
        )

    return _status(
        status="verified",
        reason="Agent365 extension/runtime packages are installed and importable.",
        runtime_observability="a365-exporter",
        settings=safe_defaults,
    )


def main() -> int:
    import os

    status = evaluate_agent365_observability_readiness(env=dict(os.environ))
    print(json.dumps(status, indent=2))
    if status["status"] == "failed":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

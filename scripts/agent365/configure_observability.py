from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

MICROSOFT_OTEL_DISTRO_PACKAGE = "microsoft-opentelemetry"
A365_EXTENSION_PACKAGES = [
    "microsoft-agents-a365-observability-extensions-agent-framework",
    "microsoft-agents-a365-observability-core",
    "microsoft-agents-a365-runtime",
]


@dataclass
class PackageIndexClient:
    timeout_seconds: float = 3.0

    def has_package(self, package_name: str) -> bool:
        url = f"https://pypi.org/pypi/{package_name}/json"
        request = urllib.request.Request(url=url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return response.status == 200
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise


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
    prefer_microsoft_otel_distro: bool = True,
) -> dict[str, Any]:
    package_index = package_index or PackageIndexClient()

    safe_defaults = {
        "a365_suppress_invoke_agent_input": True,
    }

    if prefer_microsoft_otel_distro and package_index.has_package(MICROSOFT_OTEL_DISTRO_PACKAGE):
        return _status(
            status="verified",
            reason=(
                "Microsoft OpenTelemetry distro is available for "
                "Agent 365 observability integration."
            ),
            runtime_observability="microsoft-otel-distro",
            settings=safe_defaults,
        )

    missing_packages = [
        pkg for pkg in A365_EXTENSION_PACKAGES if not package_index.has_package(pkg)
    ]
    if missing_packages:
        return _status(
            status="prerequisite-skipped",
            reason=(
                "Agent 365 package prerequisites are unavailable from the package index: "
                + ", ".join(missing_packages)
            ),
            runtime_observability="app-insights",
            settings=safe_defaults,
        )

    return _status(
        status="verified",
        reason="Agent 365 extension packages are available.",
        runtime_observability="a365-extension-packages",
        settings=safe_defaults,
    )


def main() -> int:
    status = evaluate_agent365_observability_readiness()
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_microsoft_observability_entrypoint() -> Callable[..., None] | None:
    try:
        module = importlib.import_module("microsoft.opentelemetry")
    except Exception:
        return None

    return getattr(module, "use_microsoft_opentelemetry", None)


def configure_observability(department: str) -> None:
    use_microsoft_opentelemetry = _load_microsoft_observability_entrypoint()
    enable_a365_exporter = _is_truthy(os.getenv("ENABLE_A365_OBSERVABILITY_EXPORTER"))

    if use_microsoft_opentelemetry is None:
        logger.warning(
            "microsoft-opentelemetry is not installed; observability exporter is disabled for %s.",
            department,
        )
        return

    kwargs: dict[str, Any] = {
        "enable_sensitive_data": False,
        "enable_a365": enable_a365_exporter,
        "a365_enable_observability_exporter": enable_a365_exporter,
        "a365_suppress_invoke_agent_input": True,
        "enable_console": not enable_a365_exporter,
    }

    use_microsoft_opentelemetry(**kwargs)


__all__ = ["configure_observability"]

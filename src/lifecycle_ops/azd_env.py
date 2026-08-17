from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping


def parse_values(raw_env: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw_env.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_values(*, ignore_errors: bool = False) -> dict[str, str]:
    try:
        result = subprocess.run(
            ["azd", "env", "get-values", "--no-prompt"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        if ignore_errors:
            return {}
        raise
    return parse_values(result.stdout)


def set_value(name: str, value: str) -> None:
    subprocess.run(
        ["azd", "env", "set", name, value, "--no-prompt"],
        check=True,
        capture_output=True,
        text=True,
    )


def resolve_value(name: str, values: Mapping[str, str], *, default: str = "") -> str:
    """Look up an environment value in the process environment, then in ``values``.

    Each source is searched in turn, and within a source the exact name wins before a
    case-insensitive match. azd restores ARM output names with inconsistent casing
    (``FOUNDRYIQ_SEARCH_ENDPOINT_SHARED`` comes back as
    ``foundryiQ_SEARCH_ENDPOINT_SHARED``) while ``os.environ`` only ignores case on
    Windows, so searching per source keeps the process environment authoritative and
    the result identical on every platform.

    Switching infrastructure providers can leave both spellings in one source, so
    without the exact-match preference the winner would depend on dictionary order.
    """
    lowered = name.lower()

    for source in (os.environ, values):
        value = source.get(name)
        if value:
            return value

        for key, candidate in source.items():
            if key.lower() == lowered and candidate:
                return candidate

    return default

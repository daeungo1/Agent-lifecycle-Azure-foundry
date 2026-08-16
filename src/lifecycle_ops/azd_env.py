from __future__ import annotations

import subprocess


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

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

AGENT_SMOKE_PROMPTS = {
    "development-agent": "development",
    "human-resources-agent": "human-resources",
    "marketing-agent": "marketing",
}

ACTIVE_STATUSES = {"active", "running", "succeeded", "ready"}


def parse_azd_env_values(raw_env: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw_env.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def run_command(args: list[str], *, capture_json: bool = False) -> Any:
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        message = stderr or stdout or "Command failed"
        raise RuntimeError(f"{' '.join(args)} -> {message}")

    output = completed.stdout
    if capture_json:
        text = output.strip()
        if not text:
            return {}
        return json.loads(text)
    return output


def _normalize_status(show_payload: Any) -> str:
    if not isinstance(show_payload, dict):
        return "unknown"

    candidates = [
        show_payload.get("status"),
        show_payload.get("state"),
        show_payload.get("provisioningState"),
    ]
    properties = show_payload.get("properties")
    if isinstance(properties, dict):
        candidates.extend(
            [
                properties.get("status"),
                properties.get("state"),
                properties.get("provisioningState"),
            ]
        )

    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return "unknown"


def verify_agents(*, smoke_artifacts_dir: str) -> dict[str, Any]:
    env_raw = str(run_command(["azd", "env", "get-values", "--no-prompt"]))
    env_values = parse_azd_env_values(env_raw)
    artifact_path = Path(smoke_artifacts_dir)

    summary: dict[str, Any] = {
        "status": "success",
        "environment": env_values.get("AZURE_ENV_NAME", ""),
        "smokeArtifactsDir": str(artifact_path),
        "agents": {},
        "failures": [],
    }

    for agent_name, department in AGENT_SMOKE_PROMPTS.items():
        show_payload = run_command(
            [
                "azd",
                "ai",
                "agent",
                "show",
                agent_name,
                "--output",
                "json",
                "--no-prompt",
            ],
            capture_json=True,
        )
        status = _normalize_status(show_payload)

        smoke_file = artifact_path.joinpath(f"smoke-{department}.txt")
        smoke_output = ""
        if smoke_file.exists():
            smoke_output = smoke_file.read_text(encoding="utf-8").strip()
        else:
            summary["failures"].append(
                f"Missing smoke artifact for '{agent_name}': {smoke_file}"
            )

        summary["agents"][agent_name] = {
            "status": status,
            "smoke_response": smoke_output,
            "smoke_artifact": str(smoke_file),
        }

        if status not in ACTIVE_STATUSES:
            expected = ", ".join(sorted(ACTIVE_STATUSES))
            summary["failures"].append(
                f"Agent '{agent_name}' status is '{status}' (expected one of {expected})."
            )
        if not smoke_output:
            summary["failures"].append(
                f"Smoke artifact for '{agent_name}' is missing or empty: {smoke_file}"
            )

    if summary["failures"]:
        summary["status"] = "failure"

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", default="", help="Write summary JSON to this file path")
    parser.add_argument(
        "--smoke-artifacts-dir",
        default="artifacts",
        help="Directory containing precomputed smoke-*.txt files",
    )
    args = parser.parse_args(argv)

    try:
        summary = verify_agents(smoke_artifacts_dir=str(args.smoke_artifacts_dir))
    except Exception as exc:
        summary = {
            "status": "failure",
            "agents": {},
            "failures": [str(exc)],
        }

    rendered = json.dumps(summary, indent=2)
    print(rendered)

    output_path = str(args.output_json).strip()
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")

    return 0 if summary.get("status") == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
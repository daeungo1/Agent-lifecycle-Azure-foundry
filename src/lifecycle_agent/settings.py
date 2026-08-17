from __future__ import annotations

from dataclasses import dataclass

from .departments import load_departments

REQUIRED_ENV_VARS = (
    "DEPARTMENT",
    "FOUNDRY_PROJECT_ENDPOINT",
    "AZURE_AI_MODEL_DEPLOYMENT_NAME",
    "TOOLBOX_ENDPOINT",
)
RESPONSES_PROTOCOL_VERSION = "2.0.0"


@dataclass(frozen=True)
class Settings:
    department: str
    foundry_project_endpoint: str
    azure_ai_model_deployment_name: str
    toolbox_endpoint: str
    responses_protocol_version: str

    @classmethod
    def from_env(cls) -> "Settings":
        import os

        missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
        if missing:
            missing_list = ", ".join(missing)
            raise ValueError(f"Missing required environment variables: {missing_list}")

        department = os.environ["DEPARTMENT"]
        if department not in load_departments():
            raise ValueError(f"Unknown department: {department}")

        return cls(
            department=department,
            foundry_project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            azure_ai_model_deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            toolbox_endpoint=os.environ["TOOLBOX_ENDPOINT"],
            responses_protocol_version=RESPONSES_PROTOCOL_VERSION,
        )

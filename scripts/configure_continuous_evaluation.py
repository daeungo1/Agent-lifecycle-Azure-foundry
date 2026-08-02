from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

try:
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        ContinuousEvaluationRuleAction,
        EvaluationRule,
        EvaluationRuleEventType,
        EvaluationRuleFilter,
    )
except ModuleNotFoundError:  # pragma: no cover - covered by unit tests with fallback models
    AIProjectClient = Any  # type: ignore[assignment]

    @dataclass
    class ContinuousEvaluationRuleAction:  # type: ignore[no-redef]
        eval_id: str
        max_hourly_runs: int

    @dataclass
    class EvaluationRuleFilter:  # type: ignore[no-redef]
        agent_name: str

    class EvaluationRuleEventType:  # type: ignore[no-redef]
        RESPONSE_COMPLETED = "response_completed"

    @dataclass
    class EvaluationRule:  # type: ignore[no-redef]
        id: str
        display_name: str
        description: str
        enabled: bool
        event_type: str
        filter: EvaluationRuleFilter
        action: ContinuousEvaluationRuleAction

from azure.identity import DefaultAzureCredential

DEFAULT_MAX_HOURLY_RUNS = 20
BUILTIN_EVALUATORS = ["intent_resolution", "task_adherence", "relevance"]
TESTING_CRITERIA = [
    {
        "type": "azure_ai_evaluator",
        "name": "intent_resolution",
        "evaluator_name": "builtin.intent_resolution",
    },
    {
        "type": "azure_ai_evaluator",
        "name": "task_adherence",
        "evaluator_name": "builtin.task_adherence",
    },
    {
        "type": "azure_ai_evaluator",
        "name": "relevance",
        "evaluator_name": "builtin.relevance",
    },
]
DEPARTMENT_AGENT_NAMES = {
    "development": "development-agent",
    "human-resources": "human-resources-agent",
    "marketing": "marketing-agent",
}


def _bounded_hourly_runs(max_hourly_runs: int) -> int:
    return max(1, min(max_hourly_runs, DEFAULT_MAX_HOURLY_RUNS))


def _iter_items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, (str, bytes, dict)):
        return []

    data = getattr(value, "data", None)
    if isinstance(data, list):
        return data
    if isinstance(data, tuple):
        return list(data)
    if isinstance(data, Iterable) and not isinstance(data, (str, bytes, dict)):
        return list(data)

    if isinstance(value, Iterable):
        return list(value)

    return []


def _build_eval_name(department: str) -> str:
    return f"continuous-eval-{department}"


def _build_rule_id(department: str) -> str:
    return f"continuous-response-completed-{department}"


def _find_eval_id_by_name(*, openai_client: Any, eval_name: str) -> str | None:
    evals_api = getattr(openai_client, "evals", None)
    if evals_api is None:
        raise RuntimeError("OpenAI evals API is unavailable on the project OpenAI client.")

    list_fn = getattr(evals_api, "list", None)
    if not callable(list_fn):
        raise RuntimeError("OpenAI evals.list is unavailable on the project OpenAI client.")

    try:
        existing = _iter_items(list_fn())
    except Exception as exc:
        raise RuntimeError(f"OpenAI evals.list failed: {exc}") from exc

    for item in existing:
        if getattr(item, "name", None) == eval_name:
            eval_id = getattr(item, "id", None)
            if isinstance(eval_id, str) and eval_id:
                return eval_id
    return None


def _create_eval_definition(*, openai_client: Any, eval_name: str) -> str:
    evals_api = getattr(openai_client, "evals", None)
    create_fn = getattr(evals_api, "create", None)
    if not callable(create_fn):
        raise RuntimeError("OpenAI evals.create is unavailable on the project OpenAI client.")

    created = create_fn(
        name=eval_name,
        data_source_config={"type": "azure_ai_source", "scenario": "responses"},
        testing_criteria=TESTING_CRITERIA,
    )
    eval_id = getattr(created, "id", None)
    if not isinstance(eval_id, str) or not eval_id:
        raise RuntimeError(f"Created eval '{eval_name}' did not return a valid id.")
    return eval_id


def configure_continuous_evaluation(
    *,
    project_client: Any,
    openai_client: Any | None = None,
    max_hourly_runs: int = DEFAULT_MAX_HOURLY_RUNS,
) -> list[dict[str, str]]:
    if openai_client is None:
        openai_client = project_client.get_openai_client()
    bounded_runs = _bounded_hourly_runs(max_hourly_runs)
    configured: list[dict[str, str]] = []

    for department, agent_name in DEPARTMENT_AGENT_NAMES.items():
        eval_name = _build_eval_name(department)
        eval_id = _find_eval_id_by_name(openai_client=openai_client, eval_name=eval_name)
        if eval_id is None:
            eval_id = _create_eval_definition(openai_client=openai_client, eval_name=eval_name)

        action = ContinuousEvaluationRuleAction(
            eval_id=eval_id,
            max_hourly_runs=bounded_runs,
        )
        rule = EvaluationRule(
            id=_build_rule_id(department),
            display_name=f"Continuous evaluation for {department}",
            description=(
                f"Runs response-completed continuous evaluation for {agent_name} "
                f"using builtin evaluators: {', '.join(BUILTIN_EVALUATORS)}"
            ),
            enabled=True,
            event_type=EvaluationRuleEventType.RESPONSE_COMPLETED,
            filter=EvaluationRuleFilter(agent_name=agent_name),
            action=action,
        )
        project_client.evaluation_rules.create_or_update(_build_rule_id(department), rule)

        configured.append(
            {
                "department": department,
                "agent_name": agent_name,
                "eval_name": eval_name,
                "eval_id": eval_id,
                "rule_id": _build_rule_id(department),
            }
        )

    return configured


def _create_project_client(credential: DefaultAzureCredential) -> Any:
    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT") or os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    if not endpoint:
        raise RuntimeError(
            "Set FOUNDRY_PROJECT_ENDPOINT (preferred) or AZURE_AI_PROJECT_ENDPOINT "
            "before running."
        )

    return AIProjectClient(endpoint=endpoint, credential=credential)


def main() -> int:
    credential = DefaultAzureCredential()
    project_client = None
    openai_client = None
    try:
        project_client = _create_project_client(credential)
        openai_client = project_client.get_openai_client()
        configured = configure_continuous_evaluation(
            project_client=project_client,
            openai_client=openai_client,
        )
        print(json.dumps({"configured_rules": configured}, indent=2))
        return 0
    finally:
        if openai_client is not None:
            close_openai = getattr(openai_client, "close", None)
            if callable(close_openai):
                close_openai()
        if project_client is not None:
            close_client = getattr(project_client, "close", None)
            if callable(close_client):
                close_client()
        close_credential = getattr(credential, "close", None)
        if callable(close_credential):
            close_credential()


if __name__ == "__main__":
    raise SystemExit(main())

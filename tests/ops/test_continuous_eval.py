from __future__ import annotations

import builtins
import runpy
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from lifecycle_ops.provisioning.continuous_eval import (
    DEFAULT_MAX_HOURLY_RUNS,
    DEPARTMENT_AGENT_NAMES,
    _create_project_client,
    _iter_items,
    configure_continuous_evaluation,
)


@dataclass
class _FakeEval:
    id: str
    name: str


class _FakeEvalsApi:
    def __init__(
        self,
        existing: list[_FakeEval],
        *,
        list_result: object | None = None,
        list_error: Exception | None = None,
    ) -> None:
        self._existing = existing
        self._list_result = list_result
        self._list_error = list_error
        self.created: list[dict[str, object]] = []

    def list(self):
        if self._list_error is not None:
            raise self._list_error
        if self._list_result is not None:
            return self._list_result
        return list(self._existing)

    def create(self, **kwargs):
        self.created.append(kwargs)
        created = _FakeEval(id=f"eval-{len(self.created)}", name=str(kwargs["name"]))
        self._existing.append(created)
        return created


class _FakeOpenAIClient:
    def __init__(self, evals_api: _FakeEvalsApi) -> None:
        self.evals = evals_api
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeEvaluationRulesApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def create_or_update(self, rule_id: str, rule: object) -> None:
        self.calls.append((rule_id, rule))


class _FakeProjectClient:
    def __init__(self, *, openai_client: _FakeOpenAIClient) -> None:
        self._openai_client = openai_client
        self.evaluation_rules = _FakeEvaluationRulesApi()

    def get_openai_client(self) -> _FakeOpenAIClient:
        return self._openai_client


class _IterablePager:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _DataTupleContainer:
    def __init__(self, rows: tuple[object, ...]) -> None:
        self.data = rows


def test_configure_continuous_evaluation_reuses_existing_eval_by_name() -> None:
    existing = [_FakeEval(id="eval-existing-dev", name="continuous-eval-development")]
    evals_api = _FakeEvalsApi(existing=existing)
    project_client = _FakeProjectClient(openai_client=_FakeOpenAIClient(evals_api=evals_api))

    result = configure_continuous_evaluation(project_client=project_client, max_hourly_runs=50)

    # One deterministic definition per department.
    assert len(result) == 3
    assert len(evals_api.created) == 2
    created_names = {str(entry["name"]) for entry in evals_api.created}
    assert created_names == {
        "continuous-eval-human-resources",
        "continuous-eval-marketing",
    }

    # All rules are configured and bounded conservatively.
    assert len(project_client.evaluation_rules.calls) == 3
    for rule_id, rule in project_client.evaluation_rules.calls:
        assert rule_id.startswith("continuous-response-completed-")
        assert getattr(rule, "display_name")
        assert getattr(rule, "description")
        assert getattr(rule, "enabled") is True
        assert getattr(rule.action, "max_hourly_runs") <= DEFAULT_MAX_HOURLY_RUNS
        assert getattr(rule.action, "max_hourly_runs") == DEFAULT_MAX_HOURLY_RUNS
        eval_id = getattr(rule.action, "eval_id")
        assert eval_id.startswith("eval-") or eval_id.startswith("eval-existing")


def test_configure_continuous_evaluation_uses_department_filters_and_response_completed() -> None:
    evals_api = _FakeEvalsApi(existing=[])
    project_client = _FakeProjectClient(openai_client=_FakeOpenAIClient(evals_api=evals_api))

    configure_continuous_evaluation(project_client=project_client, max_hourly_runs=8)

    assert len(evals_api.created) == 3
    for payload in evals_api.created:
        assert payload["data_source_config"] == {
            "type": "azure_ai_source",
            "scenario": "responses",
        }
        assert payload["testing_criteria"] == [
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

    assert len(project_client.evaluation_rules.calls) == 3
    seen_agents = set()
    for _, rule in project_client.evaluation_rules.calls:
        seen_agents.add(getattr(rule.filter, "agent_name"))
        event_type = str(getattr(rule, "event_type")).lower()
        assert "response" in event_type
        assert "completed" in event_type

    assert seen_agents == set(DEPARTMENT_AGENT_NAMES.values())


def test_iter_items_accepts_data_tuple_and_iterable_pager() -> None:
    rows = [SimpleNamespace(id="eval-1", name="continuous-eval-development")]

    assert _iter_items(_DataTupleContainer(tuple(rows))) == rows
    assert _iter_items(_IterablePager(rows)) == rows


def test_iter_items_rejects_string_and_dict_iterables() -> None:
    assert _iter_items("abc") == []
    assert _iter_items({"id": "eval-1"}) == []


def test_configure_continuous_evaluation_fails_when_list_api_errors() -> None:
    evals_api = _FakeEvalsApi(existing=[], list_error=RuntimeError("list unavailable"))
    project_client = _FakeProjectClient(openai_client=_FakeOpenAIClient(evals_api=evals_api))

    with pytest.raises(RuntimeError, match="list unavailable"):
        configure_continuous_evaluation(project_client=project_client)


def test_configure_continuous_evaluation_fails_when_list_api_missing() -> None:
    openai_client = SimpleNamespace(evals=SimpleNamespace(create=lambda **_: None))
    project_client = _FakeProjectClient(openai_client=openai_client)

    with pytest.raises(RuntimeError, match="evals.list"):
        configure_continuous_evaluation(project_client=project_client)


def test_create_project_client_requires_foundry_project_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.foundry.azure.com")
    monkeypatch.delenv("AZURE_AI_PROJECT_ENDPOINT", raising=False)

    created: dict[str, object] = {}

    class _FakeClient:
        def __init__(self, *, endpoint: str, credential: object) -> None:
            created["endpoint"] = endpoint
            created["credential"] = credential

    monkeypatch.setattr("lifecycle_ops.provisioning.continuous_eval.AIProjectClient", _FakeClient)
    credential = object()

    _create_project_client(credential)  # type: ignore[arg-type]

    assert created["endpoint"] == "https://example.foundry.azure.com"
    assert created["credential"] is credential


def test_create_project_client_supports_azure_ai_project_endpoint_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.setenv("AZURE_AI_PROJECT_ENDPOINT", "https://alias.foundry.azure.com")

    created: dict[str, object] = {}

    class _FakeClient:
        def __init__(self, *, endpoint: str, credential: object) -> None:
            created["endpoint"] = endpoint
            created["credential"] = credential

    monkeypatch.setattr("lifecycle_ops.provisioning.continuous_eval.AIProjectClient", _FakeClient)

    _create_project_client(object())  # type: ignore[arg-type]

    assert created["endpoint"] == "https://alias.foundry.azure.com"


def test_create_project_client_fails_without_supported_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_AI_PROJECT_ENDPOINT", raising=False)
    monkeypatch.setenv("AZURE_FOUNDRY_PROJECT_CONNECTION_STRING", "Endpoint=legacy")

    with pytest.raises(RuntimeError, match="FOUNDRY_PROJECT_ENDPOINT"):
        _create_project_client(object())  # type: ignore[arg-type]


def test_fallback_evaluation_rule_accepts_full_constructor_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "lifecycle_ops"
        / "provisioning"
        / "continuous_eval.py"
    )
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("azure.ai.projects"):
            raise ModuleNotFoundError("forced fallback import")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    namespace = runpy.run_path(str(script_path), run_name="fallback_eval_rule_module")

    action = namespace["ContinuousEvaluationRuleAction"](
        eval_id="eval-123",
        max_hourly_runs=5,
    )
    rule_filter = namespace["EvaluationRuleFilter"](agent_name="development-agent")
    rule = namespace["EvaluationRule"](
        id="rule-123",
        display_name="rule name",
        description="rule description",
        enabled=True,
        event_type="response_completed",
        filter=rule_filter,
        action=action,
    )

    assert rule.id == "rule-123"
    assert rule.display_name == "rule name"
    assert rule.description == "rule description"
    assert rule.enabled is True

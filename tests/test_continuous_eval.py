from __future__ import annotations

from dataclasses import dataclass

from scripts.configure_continuous_evaluation import (
    DEFAULT_MAX_HOURLY_RUNS,
    DEPARTMENT_AGENT_NAMES,
    configure_continuous_evaluation,
)


@dataclass
class _FakeEval:
    id: str
    name: str


class _FakeEvalsApi:
    def __init__(self, existing: list[_FakeEval]) -> None:
        self._existing = existing
        self.created: list[dict[str, object]] = []

    def list(self):
        return list(self._existing)

    def create(self, **kwargs):
        self.created.append(kwargs)
        created = _FakeEval(id=f"eval-{len(self.created)}", name=str(kwargs["name"]))
        self._existing.append(created)
        return created


class _FakeOpenAIClient:
    def __init__(self, evals_api: _FakeEvalsApi) -> None:
        self.evals = evals_api


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
        assert payload["testing_criteria"] == ["intent_resolution", "task_adherence", "relevance"]
        assert payload["data_source_config"] == {"type": "response_completed"}

    assert len(project_client.evaluation_rules.calls) == 3
    seen_agents = set()
    for _, rule in project_client.evaluation_rules.calls:
        seen_agents.add(getattr(rule.filter, "agent_name"))
        event_type = str(getattr(rule, "event_type")).lower()
        assert "response" in event_type
        assert "completed" in event_type

    assert seen_agents == set(DEPARTMENT_AGENT_NAMES.values())

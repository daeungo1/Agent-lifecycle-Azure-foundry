from pathlib import Path

from src.lifecycle_agent.config import DepartmentConfig, Settings, SpecialistConfig
from src.lifecycle_agent.orchestration import build_department_agent, build_toolbox


class _Token:
    def __init__(self, token: str) -> None:
        self.token = token


class _Credential:
    def __init__(self) -> None:
        self.scopes: list[str] = []

    def get_token(self, scope: str) -> _Token:
        self.scopes.append(scope)
        return _Token("token-value")


def _settings() -> Settings:
    return Settings(
        department="development",
        foundry_project_endpoint="https://example.services.ai.azure.com/api/projects/demo",
        azure_ai_model_deployment_name="gpt-5.4-mini",
        toolbox_endpoint="https://example.toolbox",
        responses_protocol_version="2.0.0",
    )


def _department() -> DepartmentConfig:
    return DepartmentConfig(
        name="development",
        description="Development department lifecycle assistant.",
        prompt_path=Path("src/lifecycle_agent/prompts/development.md"),
        specialists=(
            SpecialistConfig("architecture-specialist", "Architecture specialist."),
            SpecialistConfig("code-quality-specialist", "Code quality specialist."),
        ),
    )


def test_build_toolbox_is_authenticated_and_lazy(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeMCPStreamableHTTPTool:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "src.lifecycle_agent.toolbox.MCPStreamableHTTPTool",
        FakeMCPStreamableHTTPTool,
    )

    credential = _Credential()
    tool = build_toolbox("https://example.toolbox", credential)

    assert isinstance(tool, FakeMCPStreamableHTTPTool)
    assert captured["name"] == "department-toolbox"
    assert captured["url"] == "https://example.toolbox"
    assert captured["load_tools"] is False
    assert captured["load_prompts"] is False

    headers = captured["header_provider"]({})
    assert headers == {"Authorization": "Bearer token-value"}
    assert credential.scopes == ["https://ai.azure.com/.default"]


def test_build_department_agent_attaches_two_specialists_and_one_toolbox(monkeypatch) -> None:
    build_calls: list[dict[str, object]] = []
    as_tool_calls: list[tuple[str, str]] = []
    coordinator_tools: list[object] = []

    class FakeAgent:
        def __init__(self, client, instructions=None, **kwargs):
            record = {
                "client": client,
                "instructions": instructions,
                "kwargs": kwargs,
            }
            build_calls.append(record)
            self._name = kwargs.get("name", "")

        def as_tool(self, *, name=None, description=None, **_kwargs):
            as_tool_calls.append((name, description))
            return {"tool_name": name, "description": description}

    class FakeFoundryChatClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    toolbox_sentinel = object()

    def fake_build_toolbox(endpoint, credential):
        assert endpoint == "https://example.toolbox"
        assert credential is not None
        return toolbox_sentinel

    monkeypatch.setattr("src.lifecycle_agent.orchestration.Agent", FakeAgent)
    monkeypatch.setattr(
        "src.lifecycle_agent.orchestration.FoundryChatClient",
        FakeFoundryChatClient,
    )
    monkeypatch.setattr("src.lifecycle_agent.orchestration.build_toolbox", fake_build_toolbox)

    coordinator = build_department_agent(_department(), _settings(), _Credential())

    assert isinstance(coordinator, FakeAgent)
    assert len(build_calls) == 3

    coordinator_record = build_calls[2]
    coordinator_tools = coordinator_record["kwargs"]["tools"]
    assert len(coordinator_tools) == 3
    assert coordinator_tools[2] is toolbox_sentinel

    assert as_tool_calls == [
        ("architecture-specialist", "Architecture specialist."),
        ("code-quality-specialist", "Code quality specialist."),
    ]
    assert coordinator_record["kwargs"]["default_options"] == {"store": False}

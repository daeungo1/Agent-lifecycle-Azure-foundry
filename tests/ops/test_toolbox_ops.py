from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import lifecycle_ops.provisioning.toolboxes as toolboxes
from lifecycle_ops.provisioning.toolboxes import (
    AUDIENCE,
    DEPARTMENT_TOOLBOXES,
    build_connection_assert_args,
    build_connection_create_args,
    build_connection_show_args,
    build_reconciliation_operations,
    build_toolbox_connection_add_args,
    build_toolbox_connection_remove_args,
    build_toolbox_create_args,
    build_toolbox_publish_args,
    ensure_exact_connection_set,
    expected_toolbox_connections,
    extract_mutation_version,
    extract_toolbox_connection_names,
    extract_toolbox_endpoint,
    plan_toolbox_reconciliation,
)


def test_expected_toolbox_connections_include_only_shared_and_own() -> None:
    assert expected_toolbox_connections("development") == [
        "kb-shared-remote-tool",
        "kb-development-remote-tool",
    ]
    assert expected_toolbox_connections("human-resources") == [
        "kb-shared-remote-tool",
        "kb-human-resources-remote-tool",
    ]
    assert expected_toolbox_connections("marketing") == [
        "kb-shared-remote-tool",
        "kb-marketing-remote-tool",
    ]


def test_load_toolbox_connections_uses_declared_yaml_boundary(tmp_path: Path) -> None:
    toolbox_path = tmp_path / "development.yaml"
    toolbox_path.write_text(
        "connections:\n  - name: kb-shared-remote-tool\n  - name: kb-development-remote-tool\n",
        encoding="utf-8",
    )

    assert toolboxes.load_toolbox_connections(toolbox_path) == [
        "kb-shared-remote-tool",
        "kb-development-remote-tool",
    ]


def test_ensure_azd_support_reports_missing_toolbox_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_toolbox(command: list[str]) -> str:
        raise subprocess.CalledProcessError(2, command)

    monkeypatch.setattr(toolboxes, "_run_raw", fail_toolbox)

    with pytest.raises(RuntimeError, match="does not support 'azd ai toolbox'"):
        toolboxes._ensure_azd_support()


def test_connection_create_args_use_agentic_identity_and_audience() -> None:
    args = build_connection_create_args(
        connection_name="kb-shared-remote-tool",
        endpoint="https://example.search.windows.net/knowledgebases/kb/mcp?api-version=2026-04-01",
    )

    assert args[:4] == ["azd", "ai", "connection", "create"]
    assert "--kind" in args
    assert args[args.index("--kind") + 1] == "remote-tool"
    assert "--auth-type" in args
    assert args[args.index("--auth-type") + 1] == "agentic-identity"
    assert "--audience" in args
    assert args[args.index("--audience") + 1] == AUDIENCE
    assert "--no-prompt" in args


def test_toolbox_create_and_publish_args_are_non_interactive() -> None:
    spec = DEPARTMENT_TOOLBOXES["development"]

    create_args = build_toolbox_create_args(spec)
    publish_args = build_toolbox_publish_args(spec.toolbox_name, "v2")

    assert create_args[:4] == ["azd", "ai", "toolbox", "create"]
    assert "--from-file" in create_args
    assert "--no-prompt" in create_args

    assert publish_args[:4] == ["azd", "ai", "toolbox", "publish"]
    assert publish_args[4:6] == [spec.toolbox_name, "v2"]
    assert "--no-prompt" in publish_args


def test_connection_verify_args_use_show_and_list_not_update() -> None:
    project_id = (
        "/subscriptions/s1/resourceGroups/rg1/providers/Microsoft.CognitiveServices/"
        "accounts/a1/projects/p1"
    )
    show_args = build_connection_show_args(project_id, "kb-shared-remote-tool")
    assert_args = build_connection_assert_args("kb-shared-remote-tool")

    assert show_args[:4] == ["az", "rest", "--method", "get"]
    assert show_args[4:6] == [
        "--url",
        (
            "https://management.azure.com"
            f"{project_id}/connections/kb-shared-remote-tool"
            "?api-version=2025-04-01-preview"
        ),
    ]
    assert "update" not in " ".join(show_args)
    assert assert_args[:4] == ["azd", "ai", "connection", "list"]


def test_extract_toolbox_connection_names_recursively() -> None:
    payload = {
        "name": "development-knowledge-toolbox",
        "defaultVersion": {
            "tools": [
                {
                    "type": "mcp",
                    "project_connection_id": "kb-shared-remote-tool",
                },
                {
                    "nested": {
                        "tools": [
                            {"project_connection_id": "kb-development-remote-tool"},
                        ]
                    }
                },
            ],
            "connections": [
                {"name": "kb-shared-remote-tool"},
                {"name": "kb-development-remote-tool"},
            ],
        },
    }

    assert extract_toolbox_connection_names(payload) == {
        "kb-shared-remote-tool",
        "kb-development-remote-tool",
    }


def test_extract_toolbox_endpoint_explicit_or_constructed() -> None:
    explicit = {
        "version": {
            "details": {"mcpEndpoint": "https://example.invalid/toolboxes/dev/mcp?api-version=v1"}
        }
    }
    assert extract_toolbox_endpoint(explicit) == ""

    fallback = extract_toolbox_endpoint(
        {"name": "development-knowledge-toolbox"},
        project_endpoint="https://example.services.ai.azure.com/api/projects/p1",
        toolbox_name="development-knowledge-toolbox",
    )
    assert (
        fallback
        == "https://example.services.ai.azure.com/api/projects/p1/toolboxes/development-knowledge-toolbox/mcp?api-version=v1"
    )

    # Nested endpoint-like values must not influence deterministic endpoint generation.
    poisoned = extract_toolbox_endpoint(
        {
            "version": {
                "details": {
                    "endpoint": "https://attacker.invalid/toolboxes/poison/mcp?api-version=v1",
                    "url": "https://attacker.invalid/other",
                }
            }
        },
        project_endpoint="https://example.services.ai.azure.com/api/projects/p1/",
        toolbox_name="development-knowledge-toolbox",
    )
    assert (
        poisoned
        == "https://example.services.ai.azure.com/api/projects/p1/toolboxes/development-knowledge-toolbox/mcp?api-version=v1"
    )


def test_extract_mutation_version_uses_only_mutation_payload_version_keys() -> None:
    payload = {
        "versions": [
            {"version": "v1"},
            {"version": "v2"},
        ],
        "mutation": {
            "result": {
                "toolboxVersion": "v3",
                "id": "not-a-version-source",
                "name": "also-not-a-version-source",
            }
        },
    }

    assert extract_mutation_version(payload) == "v3"


def test_extract_mutation_version_fails_closed_when_missing_or_ambiguous() -> None:
    missing = {"mutation": {"result": {"id": "foo", "name": "bar"}}}
    ambiguous = {"first": {"toolboxVersion": "v3"}, "second": {"toolbox_version": "v4"}}

    for payload in (missing, ambiguous):
        try:
            extract_mutation_version(payload)
        except ValueError as exc:
            message = str(exc).lower()
            assert "version" in message
        else:
            raise AssertionError("expected mutation version extraction to fail closed")


def test_reconciliation_plan_handles_missing_and_extra_connections() -> None:
    plan = plan_toolbox_reconciliation(
        current={"kb-shared-remote-tool", "kb-marketing-remote-tool"},
        expected={"kb-shared-remote-tool", "kb-development-remote-tool"},
    )

    assert plan["missing"] == ["kb-development-remote-tool"]
    assert plan["extra"] == ["kb-marketing-remote-tool"]


def test_runtime_reconciliation_operations_remove_cross_department_extra_and_assert_final() -> None:
    operations = build_reconciliation_operations(
        toolbox_name="development-knowledge-toolbox",
        current={"kb-shared-remote-tool", "kb-marketing-remote-tool"},
        expected={"kb-shared-remote-tool", "kb-development-remote-tool"},
    )

    assert operations == [
        {
            "action": "add",
            "toolbox": "development-knowledge-toolbox",
            "connection": "kb-development-remote-tool",
            "publish": "mutation",
        },
        {
            "action": "remove",
            "toolbox": "development-knowledge-toolbox",
            "connection": "kb-marketing-remote-tool",
            "publish": "mutation",
        },
        {
            "action": "assert-exact",
            "toolbox": "development-knowledge-toolbox",
        },
    ]


def test_toolbox_mutation_builders_include_publishable_commands() -> None:
    add_args = build_toolbox_connection_add_args(
        toolbox_name="development-knowledge-toolbox",
        connection_name="kb-development-remote-tool",
    )
    remove_args = build_toolbox_connection_remove_args(
        toolbox_name="development-knowledge-toolbox",
        connection_name="kb-marketing-remote-tool",
    )
    assert add_args[:5] == ["azd", "ai", "toolbox", "connection", "add"]
    assert "--output" in add_args
    assert add_args[add_args.index("--output") + 1] == "json"
    assert remove_args[:5] == ["azd", "ai", "toolbox", "connection", "remove"]
    assert "--output" in remove_args
    assert remove_args[remove_args.index("--output") + 1] == "json"


def test_exact_connection_assertion_fails_closed_on_drift() -> None:
    expected = {"kb-shared-remote-tool", "kb-development-remote-tool"}
    actual = {"kb-shared-remote-tool", "kb-marketing-remote-tool"}

    try:
        ensure_exact_connection_set(
            toolbox_name="development-knowledge-toolbox",
            expected=expected,
            actual=actual,
        )
    except ValueError as exc:
        message = str(exc)
        assert "missing" in message.lower()
        assert "extra" in message.lower()
        assert "development-knowledge-toolbox" in message
    else:
        raise AssertionError("expected fail-closed drift assertion")


def test_validate_remote_tool_connection_rejects_drift() -> None:
    with pytest.raises(ValueError, match="drift detected"):
        toolboxes.validate_remote_tool_connection(
            connection_name="kb-development-remote-tool",
            expected_target="https://expected.test/knowledgebases/dev/mcp",
            details={
                "kind": "remote-tool",
                "target": "https://wrong.test/knowledgebases/dev/mcp",
                "authType": "agentic-identity",
                "audience": AUDIENCE,
            },
        )


def test_validate_remote_tool_connection_treats_default_https_port_as_equivalent() -> None:
    toolboxes.validate_remote_tool_connection(
        connection_name="kb-development-remote-tool",
        expected_target="https://example.test/knowledgebases/dev/mcp",
        details={
            "kind": "remote-tool",
            "target": "https://example.test:443/knowledgebases/dev/mcp",
            "authType": "agentic-identity",
            "audience": "https://search.azure.com:443",
        },
    )


def test_validate_remote_tool_connection_accepts_arm_agentic_identity_token() -> None:
    toolboxes.validate_remote_tool_connection(
        connection_name="kb-development-remote-tool",
        expected_target="https://example.test/knowledgebases/dev/mcp",
        details={
            "category": "RemoteTool",
            "target": "https://example.test/knowledgebases/dev/mcp",
            "authType": "AgenticIdentityToken",
            "audience": AUDIENCE,
        },
    )


def test_ensure_remote_tool_connection_creates_missing_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_commands: list[list[str]] = []
    monkeypatch.setattr(toolboxes, "_run_json", lambda command, **kwargs: [])
    monkeypatch.setattr(
        toolboxes,
        "_run_raw",
        lambda command: raw_commands.append(command) or "",
    )

    toolboxes.ensure_remote_tool_connection(
        project_id="/subscriptions/s1/resourceGroups/rg1/providers/Microsoft.CognitiveServices/accounts/a1/projects/p1",
        connection_name="kb-development-remote-tool",
        target="https://example.test/knowledgebases/dev/mcp",
    )

    assert raw_commands == [
        build_connection_create_args(
            connection_name="kb-development-remote-tool",
            endpoint="https://example.test/knowledgebases/dev/mcp",
        )
    ]


def test_ensure_remote_tool_connection_validates_existing_arm_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = (
        "/subscriptions/s1/resourceGroups/rg1/providers/Microsoft.CognitiveServices/"
        "accounts/a1/projects/p1"
    )
    commands: list[list[str]] = []

    def fake_run_json(command: list[str], **kwargs: object) -> object:
        commands.append(command)
        if command == toolboxes.build_connection_list_args():
            return [{"name": "kb-development-remote-tool"}]
        if command == build_connection_show_args(
            project_id,
            "kb-development-remote-tool",
        ):
            return {
                "properties": {
                    "category": "RemoteTool",
                    "target": "https://example.test/knowledgebases/dev/mcp",
                    "authType": "AgenticIdentityToken",
                    "audience": AUDIENCE,
                }
            }
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(toolboxes, "_run_json", fake_run_json)

    toolboxes.ensure_remote_tool_connection(
        project_id=project_id,
        connection_name="kb-development-remote-tool",
        target="https://example.test/knowledgebases/dev/mcp",
    )

    assert commands == [
        toolboxes.build_connection_list_args(),
        build_connection_show_args(project_id, "kb-development-remote-tool"),
    ]


def test_upsert_toolbox_verifies_exact_connections_and_sets_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = DEPARTMENT_TOOLBOXES["development"]
    expected = set(expected_toolbox_connections("development"))
    payload = {"connections": [{"name": name} for name in sorted(expected)]}
    env_values: list[tuple[str, str]] = []

    monkeypatch.setattr(toolboxes, "_run_json", lambda command, **kwargs: payload)
    monkeypatch.setattr(
        toolboxes,
        "set_value",
        lambda name, value: env_values.append((name, value)),
    )

    result = toolboxes.upsert_toolbox(
        spec=spec,
        project_endpoint="https://example.services.ai.azure.com/api/projects/p1",
    )

    endpoint = (
        "https://example.services.ai.azure.com/api/projects/p1/"
        "toolboxes/development-knowledge-toolbox/mcp?api-version=v1"
    )
    assert result == {
        "department": "development",
        "toolbox_name": "development-knowledge-toolbox",
        "endpoint": endpoint,
    }
    assert env_values == [("TOOLBOX_ENDPOINT_DEVELOPMENT", endpoint)]


def test_upsert_toolbox_rejects_missing_project_endpoint_before_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(
        toolboxes,
        "_run_json",
        lambda command, **kwargs: commands.append(command),
    )

    with pytest.raises(ValueError, match="Missing required FOUNDRY_PROJECT_ENDPOINT"):
        toolboxes.upsert_toolbox(
            spec=DEPARTMENT_TOOLBOXES["development"],
            project_endpoint="",
        )

    assert commands == []


def test_upsert_toolbox_dry_run_simulates_reconciled_connection_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "connections": [
            {"name": "kb-shared-remote-tool"},
            {"name": "kb-marketing-remote-tool"},
        ]
    }
    json_commands: list[list[str]] = []
    raw_commands: list[list[str]] = []
    monkeypatch.setattr(
        toolboxes,
        "_run_json",
        lambda command, **kwargs: json_commands.append(command) or payload,
    )
    monkeypatch.setattr(
        toolboxes,
        "_run_raw",
        lambda command: raw_commands.append(command) or "",
    )

    result = toolboxes.upsert_toolbox(
        spec=DEPARTMENT_TOOLBOXES["development"],
        project_endpoint="https://example.services.ai.azure.com/api/projects/p1",
        dry_run=True,
    )

    assert result == {
        "department": "development",
        "toolbox_name": "development-knowledge-toolbox",
        "endpoint": "",
    }
    assert json_commands == [toolboxes.build_toolbox_show_args("development-knowledge-toolbox")]
    assert raw_commands == []


def test_configure_toolboxes_rejects_missing_project_endpoint_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = {
        "KB_MCP_ENDPOINT_SHARED": "https://example.test/shared",
        "KB_MCP_ENDPOINT_DEVELOPMENT": "https://example.test/development",
        "KB_MCP_ENDPOINT_HUMAN_RESOURCES": "https://example.test/human-resources",
        "KB_MCP_ENDPOINT_MARKETING": "https://example.test/marketing",
    }
    mutations: list[str] = []
    monkeypatch.setattr(toolboxes, "_ensure_azd_support", lambda: None)
    monkeypatch.setattr(toolboxes, "get_values", lambda: env)
    monkeypatch.setattr(
        toolboxes,
        "ensure_remote_tool_connection",
        lambda **kwargs: mutations.append(kwargs["connection_name"]),
    )

    with pytest.raises(ValueError, match="Missing required FOUNDRY_PROJECT_ENDPOINT"):
        toolboxes.configure_toolboxes()

    assert mutations == []


def test_configure_toolboxes_preserves_connection_then_toolbox_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str]] = []
    env = {
        "FOUNDRY_PROJECT_ENDPOINT": "https://example.services.ai.azure.com/api/projects/p1",
        "AZURE_AI_PROJECT_ID": (
            "/subscriptions/s1/resourceGroups/rg1/providers/Microsoft.CognitiveServices/"
            "accounts/a1/projects/p1"
        ),
        "KB_MCP_ENDPOINT_SHARED": "https://example.test/shared",
        "KB_MCP_ENDPOINT_DEVELOPMENT": "https://example.test/development",
        "KB_MCP_ENDPOINT_HUMAN_RESOURCES": "https://example.test/human-resources",
        "KB_MCP_ENDPOINT_MARKETING": "https://example.test/marketing",
    }
    monkeypatch.setattr(toolboxes, "_ensure_azd_support", lambda: None)
    monkeypatch.setattr(toolboxes, "get_values", lambda: env)
    monkeypatch.setattr(
        toolboxes,
        "ensure_remote_tool_connection",
        lambda *, project_id, connection_name, target, dry_run=False: events.append(
            ("connection", connection_name)
        ),
    )
    monkeypatch.setattr(
        toolboxes,
        "upsert_toolbox",
        lambda *, spec, project_endpoint, dry_run=False: (
            events.append(("toolbox", spec.toolbox_name)) or {"department": spec.department}
        ),
    )

    assert toolboxes.configure_toolboxes() == [
        {"department": "development"},
        {"department": "human-resources"},
        {"department": "marketing"},
    ]
    assert events == [
        ("connection", "kb-shared-remote-tool"),
        ("connection", "kb-development-remote-tool"),
        ("connection", "kb-human-resources-remote-tool"),
        ("connection", "kb-marketing-remote-tool"),
        ("toolbox", "development-knowledge-toolbox"),
        ("toolbox", "human-resources-knowledge-toolbox"),
        ("toolbox", "marketing-knowledge-toolbox"),
    ]

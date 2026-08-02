from __future__ import annotations

from pathlib import Path

from scripts.toolbox_ops import (
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
    show_args = build_connection_show_args("kb-shared-remote-tool")
    assert_args = build_connection_assert_args("kb-shared-remote-tool")

    assert show_args[:4] == ["azd", "ai", "connection", "show"]
    assert show_args[4] == "kb-shared-remote-tool"
    assert "--output" in show_args
    assert "json" in show_args
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
        "version": {"details": {"mcpEndpoint": "https://example.invalid/toolboxes/dev/mcp?api-version=v1"}}
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


def test_static_script_asserts_publish_with_version_and_final_exact_check() -> None:
    repo = Path(__file__).resolve().parents[1]
    script = (repo / "scripts" / "configure_toolboxes.ps1").read_text(encoding="utf-8")

    assert "ai connection show" in script
    assert '"ai", "connection", "list"' in script
    assert '"ai", "toolbox", "connection", "add"' in script
    assert '"ai", "toolbox", "connection", "remove"' in script
    assert '"--output", "json"' in script
    assert '"ai", "toolbox", "publish"' in script
    assert "Get-MutationToolboxVersion" in script
    assert "FOUNDRY_PROJECT_ENDPOINT" in script
    assert "toolboxes/$ToolboxName/mcp?api-version=v1" in script
    assert '"ai", "toolbox", "versions", "list"' not in script
    assert "ensure_exact_connection_set" in script

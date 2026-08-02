from __future__ import annotations

from scripts.toolbox_ops import (
    AUDIENCE,
    DEPARTMENT_TOOLBOXES,
    build_connection_create_args,
    build_toolbox_create_args,
    build_toolbox_publish_args,
    expected_toolbox_connections,
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

    assert args[:5] == ["azd", "ai", "agent", "connection", "create"]
    assert "--auth-type" in args
    assert args[args.index("--auth-type") + 1] == "agentic-identity"
    assert "--audience" in args
    assert args[args.index("--audience") + 1] == AUDIENCE
    assert "--no-prompt" in args


def test_toolbox_create_and_publish_args_are_non_interactive() -> None:
    spec = DEPARTMENT_TOOLBOXES["development"]

    create_args = build_toolbox_create_args(spec)
    publish_args = build_toolbox_publish_args(spec.toolbox_name)

    assert create_args[:4] == ["azd", "ai", "toolbox", "create"]
    assert "--from-file" in create_args
    assert "--no-prompt" in create_args

    assert publish_args[:4] == ["azd", "ai", "toolbox", "publish"]
    assert "--no-prompt" in publish_args

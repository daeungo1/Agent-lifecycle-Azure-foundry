from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

import lifecycle_ops.provisioning.knowledge_bases as pkb
from lifecycle_ops.provisioning.knowledge_bases import (
    API_VERSION,
    KNOWLEDGE_BOUNDARIES,
    build_artifact_names,
    build_rest_operations,
    load_boundary_documents,
    search_endpoint_env_var_name,
)


def test_knowledge_boundaries_include_one_shared_and_three_private_roots() -> None:
    assert tuple(KNOWLEDGE_BOUNDARIES) == (
        "shared",
        "development",
        "human-resources",
        "marketing",
    )


def test_all_knowledge_documents_have_parseable_title_and_classification_headers() -> None:
    for boundary in KNOWLEDGE_BOUNDARIES:
        documents = load_boundary_documents(boundary)
        assert documents
        for document in documents:
            assert document.title
            assert document.classification


def test_shared_boundary_contains_only_shared_classification_documents() -> None:
    shared_documents = load_boundary_documents("shared")
    assert [document.relative_path.as_posix() for document in shared_documents] == [
        "knowledge/shared/company-handbook.md"
    ]
    assert all(document.classification == "shared" for document in shared_documents)


def test_unique_index_source_and_base_names_per_boundary() -> None:
    indexes: set[str] = set()
    sources: set[str] = set()
    bases: set[str] = set()

    for boundary in KNOWLEDGE_BOUNDARIES:
        names = build_artifact_names(prefix="enterprise-lifecycle", boundary=boundary)
        indexes.add(names.index_name)
        sources.add(names.knowledge_source_name)
        bases.add(names.knowledge_base_name)

    assert len(indexes) == 4
    assert len(sources) == 4
    assert len(bases) == 4


def test_search_endpoint_environment_variable_mapping() -> None:
    assert search_endpoint_env_var_name("shared") == "FOUNDRYIQ_SEARCH_ENDPOINT_SHARED"
    assert search_endpoint_env_var_name("development") == "FOUNDRYIQ_SEARCH_ENDPOINT_DEVELOPMENT"
    assert (
        search_endpoint_env_var_name("human-resources")
        == "FOUNDRYIQ_SEARCH_ENDPOINT_HUMAN_RESOURCES"
    )
    assert search_endpoint_env_var_name("marketing") == "FOUNDRYIQ_SEARCH_ENDPOINT_MARKETING"


def test_rest_payload_builder_uses_expected_api_shapes() -> None:
    documents = load_boundary_documents("development")
    names = build_artifact_names(prefix="enterprise-lifecycle", boundary="development")
    operations = build_rest_operations(
        boundary="development",
        endpoint="https://example.search.windows.net",
        names=names,
        documents=documents,
    )

    assert [operation["operation"] for operation in operations] == [
        "upsert-index",
        "upsert-knowledge-source",
        "upsert-knowledge-base",
        "ingest-documents",
    ]
    assert [operation["method"] for operation in operations] == ["PUT", "PUT", "PUT", "POST"]
    assert operations[0]["url"].endswith(f"/indexes/{names.index_name}?api-version={API_VERSION}")
    assert operations[1]["url"].endswith(
        f"/knowledgeSources/{names.knowledge_source_name}?api-version={API_VERSION}"
    )
    assert operations[2]["url"].endswith(
        f"/knowledgeBases/{names.knowledge_base_name}?api-version={API_VERSION}"
    )
    assert operations[3]["url"].endswith(
        f"/indexes/{names.index_name}/docs/search.index?api-version={API_VERSION}"
    )

    index_payload = operations[0]["body"]
    assert index_payload["name"] == names.index_name
    assert [field["name"] for field in index_payload["fields"]] == [
        "id",
        "title",
        "classification",
        "path",
        "content",
    ]

    source_payload = operations[1]["body"]
    assert source_payload == {
        "name": names.knowledge_source_name,
        "kind": "searchIndex",
        "description": "Knowledge source for development boundary.",
        "encryptionKey": None,
        "searchIndexParameters": {
            "searchIndexName": names.index_name,
            "semanticConfigurationName": "lifecycle-semantic",
            "sourceDataFields": [],
            "searchFields": [],
        },
    }

    base_payload = operations[2]["body"]
    assert base_payload == {
        "name": names.knowledge_base_name,
        "description": "Knowledge base for development boundary.",
        "knowledgeSources": [{"name": names.knowledge_source_name}],
        "encryptionKey": None,
    }

    ingestion_payload = operations[3]["body"]
    assert ingestion_payload["value"]
    assert all(item["@search.action"] == "mergeOrUpload" for item in ingestion_payload["value"])
    assert all(item["classification"] == "development" for item in ingestion_payload["value"])


def test_index_payload_includes_semantic_configuration_for_ga_knowledge_sources() -> None:
    names = build_artifact_names(prefix="enterprise-lifecycle", boundary="shared")
    documents = load_boundary_documents("shared")
    operations = build_rest_operations(
        boundary="shared",
        endpoint="https://example.search.windows.net",
        names=names,
        documents=documents,
    )

    index_payload = operations[0]["body"]
    assert index_payload["semantic"] == {
        "defaultConfiguration": "lifecycle-semantic",
        "configurations": [
            {
                "name": "lifecycle-semantic",
                "prioritizedFields": {
                    "titleField": {"fieldName": "title"},
                    "prioritizedContentFields": [{"fieldName": "content"}],
                },
            }
        ],
    }


def test_index_payload_omits_properties_rejected_by_search_api() -> None:
    names = build_artifact_names(prefix="enterprise-lifecycle", boundary="shared")
    documents = load_boundary_documents("shared")
    operations = build_rest_operations(
        boundary="shared",
        endpoint="https://example.search.windows.net",
        names=names,
        documents=documents,
    )

    index_payload = operations[0]["body"]
    # The Search index definition only accepts the default semantic configuration
    # nested under "semantic"; a top-level key makes the service reject the PUT
    # with 400 "The property 'defaultSemanticConfiguration' does not exist".
    assert "defaultSemanticConfiguration" not in index_payload
    assert set(index_payload) == {"name", "fields", "semantic"}


def test_parse_front_matter_supports_crlf_newlines() -> None:
    sample = "---\r\ntitle: Doc\r\nclassification: shared\r\n---\r\nHello\r\nworld\r\n"
    metadata, body = pkb._parse_front_matter(sample)

    assert metadata == {"title": "Doc", "classification": "shared"}
    assert body == "Hello\nworld"


def _set_required_endpoint_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOUNDRYIQ_SEARCH_ENDPOINT_SHARED", "https://shared.search.windows.net")
    monkeypatch.setenv("FOUNDRYIQ_SEARCH_ENDPOINT_DEVELOPMENT", "https://dev.search.windows.net")
    monkeypatch.setenv(
        "FOUNDRYIQ_SEARCH_ENDPOINT_HUMAN_RESOURCES",
        "https://hr.search.windows.net",
    )
    monkeypatch.setenv("FOUNDRYIQ_SEARCH_ENDPOINT_MARKETING", "https://mkt.search.windows.net")


def _expected_mcp_env_map(prefix: str) -> dict[str, str]:
    endpoint_by_boundary = {
        "shared": "https://shared.search.windows.net",
        "development": "https://dev.search.windows.net",
        "human-resources": "https://hr.search.windows.net",
        "marketing": "https://mkt.search.windows.net",
    }
    result: dict[str, str] = {}
    for boundary, endpoint in endpoint_by_boundary.items():
        names = build_artifact_names(prefix=prefix, boundary=boundary)
        key = f"KB_MCP_ENDPOINT_{boundary.upper().replace('-', '_')}"
        value = (
            f"{endpoint}/knowledgebases/{names.knowledge_base_name}/mcp?api-version={API_VERSION}"
        )
        result[key] = value
    return result


def test_dry_run_does_not_get_token_or_create_http_client_or_write_azd_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_endpoint_env_vars(monkeypatch)
    monkeypatch.setenv("FOUNDRYIQ_NAME_PREFIX", "enterprise-lifecycle")

    credential_ctor = Mock(side_effect=AssertionError("credential must not be created"))
    monkeypatch.setattr(pkb, "DefaultAzureCredential", credential_ctor)

    client_ctor = Mock(side_effect=AssertionError("http client must not be created"))
    monkeypatch.setattr(pkb.httpx, "Client", client_ctor)

    subprocess_calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(args: list[str], **kwargs: Any) -> Any:
        subprocess_calls.append((args, kwargs))
        if args[:3] == ["azd", "env", "get-values"]:
            return Mock(stdout="AZURE_ENV_NAME=enterprise-lifecycle\n")
        raise AssertionError("azd env set must not be called in dry-run")

    monkeypatch.setattr(pkb.subprocess, "run", fake_run)

    summary = pkb.provision_foundry_iq_knowledge(dry_run=True)

    assert summary["mode"] == "dry-run"
    assert summary["plannedEnvVars"] == _expected_mcp_env_map("enterprise-lifecycle")
    assert any(call[0][:3] == ["azd", "env", "get-values"] for call in subprocess_calls)


def test_success_persists_all_mcp_endpoints_only_after_all_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_endpoint_env_vars(monkeypatch)
    monkeypatch.setenv("FOUNDRYIQ_NAME_PREFIX", "enterprise-lifecycle")

    monkeypatch.setattr(
        pkb,
        "DefaultAzureCredential",
        lambda: Mock(get_token=lambda _scope: Mock(token="fake-token")),
    )

    http_calls: list[tuple[str, str, dict[str, Any]]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        def request(
            self,
            method: str,
            url: str,
            headers: dict[str, str],
            json: dict[str, Any],
            timeout: int,
        ) -> FakeResponse:
            http_calls.append((method, url, json))
            return FakeResponse()

    monkeypatch.setattr(pkb.httpx, "Client", lambda: FakeClient())

    subprocess_calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: Any) -> Any:
        subprocess_calls.append(args)
        if args[:3] == ["azd", "env", "get-values"]:
            return Mock(stdout="AZURE_ENV_NAME=enterprise-lifecycle\n")
        if args[:3] == ["azd", "env", "set"]:
            return Mock(stdout="")
        raise AssertionError(f"Unexpected subprocess call: {args}")

    monkeypatch.setattr(pkb.subprocess, "run", fake_run)

    summary = pkb.provision_foundry_iq_knowledge(dry_run=False)

    assert len(http_calls) == 16
    assert summary["mode"] == "apply"

    env_set_calls = [call for call in subprocess_calls if call[:3] == ["azd", "env", "set"]]
    expected_map = _expected_mcp_env_map("enterprise-lifecycle")
    assert env_set_calls == [
        ["azd", "env", "set", key, value] for key, value in expected_map.items()
    ]


def test_operation_failure_stops_before_mcp_endpoint_env_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_endpoint_env_vars(monkeypatch)
    monkeypatch.setenv("FOUNDRYIQ_NAME_PREFIX", "enterprise-lifecycle")

    class _CredentialWithClose:
        def __init__(self) -> None:
            self.closed = False

        def get_token(self, _scope: str) -> Mock:
            return Mock(token="fake-token")

        def close(self) -> None:
            self.closed = True

    credential = _CredentialWithClose()
    monkeypatch.setattr(pkb, "DefaultAzureCredential", lambda: credential)

    class FailingResponse:
        def raise_for_status(self) -> None:
            raise RuntimeError("boom")

    class FailingClient:
        def __enter__(self) -> "FailingClient":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        def request(
            self,
            method: str,
            url: str,
            headers: dict[str, str],
            json: dict[str, Any],
            timeout: int,
        ) -> FailingResponse:
            return FailingResponse()

    monkeypatch.setattr(pkb.httpx, "Client", lambda: FailingClient())

    subprocess_calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: Any) -> Any:
        subprocess_calls.append(args)
        if args[:3] == ["azd", "env", "get-values"]:
            return Mock(stdout="AZURE_ENV_NAME=enterprise-lifecycle\n")
        if args[:3] == ["azd", "env", "set"]:
            return Mock(stdout="")
        raise AssertionError(f"Unexpected subprocess call: {args}")

    monkeypatch.setattr(pkb.subprocess, "run", fake_run)

    with pytest.raises(
        RuntimeError,
        match="Search operation 'upsert-index' failed for boundary 'shared'",
    ) as exc_info:
        pkb.provision_foundry_iq_knowledge(dry_run=False)

    message = str(exc_info.value)
    assert "fake-token" not in message
    assert "@search.action" not in message
    assert credential.closed is True

    env_set_calls = [call for call in subprocess_calls if call[:3] == ["azd", "env", "set"]]
    assert env_set_calls == []


def test_apply_mode_closes_credential_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_endpoint_env_vars(monkeypatch)
    monkeypatch.setenv("FOUNDRYIQ_NAME_PREFIX", "enterprise-lifecycle")

    class _CredentialWithClose:
        def __init__(self) -> None:
            self.closed = False

        def get_token(self, _scope: str) -> Mock:
            return Mock(token="fake-token")

        def close(self) -> None:
            self.closed = True

    credential = _CredentialWithClose()
    monkeypatch.setattr(pkb, "DefaultAzureCredential", lambda: credential)

    class _Response:
        def raise_for_status(self) -> None:
            return None

    class _Client:
        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        def request(
            self,
            method: str,
            url: str,
            headers: dict[str, str],
            json: dict[str, Any],
            timeout: int,
        ) -> _Response:
            return _Response()

    monkeypatch.setattr(pkb.httpx, "Client", lambda: _Client())

    def fake_run(args: list[str], **kwargs: Any) -> Any:
        if args[:3] == ["azd", "env", "get-values"]:
            return Mock(stdout="AZURE_ENV_NAME=enterprise-lifecycle\n")
        if args[:3] == ["azd", "env", "set"]:
            return Mock(stdout="")
        raise AssertionError(f"Unexpected subprocess call: {args}")

    monkeypatch.setattr(pkb.subprocess, "run", fake_run)

    pkb.provision_foundry_iq_knowledge(dry_run=False)

    assert credential.closed is True


def test_apply_summary_exposes_boundary_artifacts_endpoints_and_operation_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_endpoint_env_vars(monkeypatch)
    monkeypatch.setenv("FOUNDRYIQ_NAME_PREFIX", "enterprise-lifecycle")

    monkeypatch.setattr(
        pkb,
        "DefaultAzureCredential",
        lambda: Mock(get_token=lambda _scope: Mock(token="fake-token")),
    )

    class _Response:
        def raise_for_status(self) -> None:
            return None

    class _Client:
        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        def request(
            self,
            method: str,
            url: str,
            headers: dict[str, str],
            json: dict[str, Any],
            timeout: int,
        ) -> _Response:
            return _Response()

    monkeypatch.setattr(pkb.httpx, "Client", lambda: _Client())

    def fake_run(args: list[str], **kwargs: Any) -> Any:
        if args[:3] == ["azd", "env", "get-values"]:
            return Mock(stdout="AZURE_ENV_NAME=enterprise-lifecycle\n")
        if args[:3] == ["azd", "env", "set"]:
            return Mock(stdout="")
        raise AssertionError(f"Unexpected subprocess call: {args}")

    monkeypatch.setattr(pkb.subprocess, "run", fake_run)

    summary = pkb.provision_foundry_iq_knowledge(dry_run=False)

    assert summary["status"] == "success"
    assert set(summary["boundaries"].keys()) == {
        "shared",
        "development",
        "human-resources",
        "marketing",
    }
    for boundary in summary["boundaries"].values():
        assert boundary["artifactNames"]["indexName"]
        assert boundary["artifactNames"]["knowledgeSourceName"]
        assert boundary["artifactNames"]["knowledgeBaseName"]
        assert boundary["mcp"]["envVarName"].startswith("KB_MCP_ENDPOINT_")
        assert boundary["mcp"]["endpoint"].startswith("https://")
        assert boundary["operationCount"] == 4
    assert "token" not in json.dumps(summary).lower()


def test_main_prints_json_and_optional_output_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = tmp_path / "knowledge-bases.json"
    monkeypatch.setattr(
        pkb.argparse.ArgumentParser,
        "parse_args",
        lambda self: Mock(dry_run=False, output=str(output_path)),
    )
    monkeypatch.setattr(
        pkb,
        "provision_foundry_iq_knowledge",
        lambda *, dry_run: {"status": "success", "mode": "apply", "boundaries": {}},
    )

    exit_code = pkb.main()

    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "success"
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "success"


def test_knowledge_roots_exist_on_disk() -> None:
    for root_path in KNOWLEDGE_BOUNDARIES.values():
        assert Path(root_path).exists()

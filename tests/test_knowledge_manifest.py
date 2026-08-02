from __future__ import annotations

from pathlib import Path

from scripts.provision_knowledge_bases import (
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
    assert (
        search_endpoint_env_var_name("development")
        == "FOUNDRYIQ_SEARCH_ENDPOINT_DEVELOPMENT"
    )
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
    assert source_payload["name"] == names.knowledge_source_name
    assert source_payload["kind"] == "azureSearchIndex"
    assert source_payload["indexName"] == names.index_name
    assert source_payload["classification"] == "development"

    base_payload = operations[2]["body"]
    assert base_payload["name"] == names.knowledge_base_name
    assert base_payload["kind"] == "searchAugmentedGeneration"
    assert base_payload["knowledgeSourceName"] == names.knowledge_source_name

    ingestion_payload = operations[3]["body"]
    assert ingestion_payload["value"]
    assert all(item["@search.action"] == "mergeOrUpload" for item in ingestion_payload["value"])
    assert all(item["classification"] == "development" for item in ingestion_payload["value"])


def test_knowledge_roots_exist_on_disk() -> None:
    for root_path in KNOWLEDGE_BOUNDARIES.values():
        assert Path(root_path).exists()
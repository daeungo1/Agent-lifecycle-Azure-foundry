from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential

API_VERSION = "2026-04-01"
SEMANTIC_CONFIGURATION_NAME = "lifecycle-semantic"
KNOWLEDGE_BOUNDARIES: dict[str, str] = {
    "shared": "knowledge/shared",
    "development": "knowledge/development",
    "human-resources": "knowledge/human-resources",
    "marketing": "knowledge/marketing",
}


@dataclass(frozen=True)
class KnowledgeDocument:
    relative_path: Path
    title: str
    classification: str
    content: str


@dataclass(frozen=True)
class ArtifactNames:
    index_name: str
    knowledge_source_name: str
    knowledge_base_name: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _normalize_token(value: str, *, max_length: int = 24) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not token:
        raise ValueError("Naming token cannot be empty after normalization.")
    return token[:max_length].rstrip("-")


def search_endpoint_env_var_name(boundary: str) -> str:
    return f"FOUNDRYIQ_SEARCH_ENDPOINT_{boundary.upper().replace('-', '_')}"


def knowledge_base_mcp_env_var_name(boundary: str) -> str:
    return f"KB_MCP_ENDPOINT_{boundary.upper().replace('-', '_')}"


def _boundary_token(boundary: str) -> str:
    tokens = {
        "shared": "shared",
        "development": "dev",
        "human-resources": "hr",
        "marketing": "mkt",
    }
    if boundary not in tokens:
        raise ValueError(f"Unknown boundary: {boundary}")
    return tokens[boundary]


def build_artifact_names(prefix: str, boundary: str) -> ArtifactNames:
    normalized_prefix = _normalize_token(prefix, max_length=16)
    boundary_segment = _boundary_token(boundary)
    stem = f"{normalized_prefix}-{boundary_segment}"
    return ArtifactNames(
        index_name=f"{stem}-idx",
        knowledge_source_name=f"{stem}-src",
        knowledge_base_name=f"{stem}-kb",
    )


def _parse_front_matter(document_text: str) -> tuple[dict[str, str], str]:
    normalized_text = document_text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized_text.startswith("---\n"):
        raise ValueError("Document is missing front matter opening delimiter.")

    marker = "\n---\n"
    end_index = normalized_text.find(marker, 4)
    if end_index == -1:
        raise ValueError("Document is missing front matter closing delimiter.")

    raw_front_matter = normalized_text[4:end_index]
    body = normalized_text[end_index + len(marker) :].strip()
    metadata: dict[str, str] = {}
    for line in raw_front_matter.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        metadata[key.strip()] = value.strip()

    return metadata, body


def load_boundary_documents(boundary: str) -> list[KnowledgeDocument]:
    if boundary not in KNOWLEDGE_BOUNDARIES:
        raise ValueError(f"Unknown boundary: {boundary}")

    root = _repo_root() / KNOWLEDGE_BOUNDARIES[boundary]
    documents: list[KnowledgeDocument] = []

    for path in sorted(root.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        metadata, body = _parse_front_matter(text)
        title = metadata.get("title", "")
        classification = metadata.get("classification", "")
        if not title:
            raise ValueError(f"Document {path.as_posix()} is missing title in front matter.")
        if not classification:
            raise ValueError(
                f"Document {path.as_posix()} is missing classification in front matter."
            )
        documents.append(
            KnowledgeDocument(
                relative_path=path.relative_to(_repo_root()),
                title=title,
                classification=classification,
                content=body,
            )
        )

    if not documents:
        raise ValueError(f"No knowledge documents found under {root.as_posix()}.")

    return documents


def _build_index_payload(index_name: str) -> dict[str, Any]:
    return {
        "name": index_name,
        "fields": [
            {
                "name": "id",
                "type": "Edm.String",
                "key": True,
                "filterable": True,
            },
            {
                "name": "title",
                "type": "Edm.String",
                "searchable": True,
            },
            {
                "name": "classification",
                "type": "Edm.String",
                "filterable": True,
                "facetable": True,
            },
            {
                "name": "path",
                "type": "Edm.String",
                "filterable": True,
            },
            {
                "name": "content",
                "type": "Edm.String",
                "searchable": True,
            },
        ],
        "semantic": {
            "defaultConfiguration": SEMANTIC_CONFIGURATION_NAME,
            "configurations": [
                {
                    "name": SEMANTIC_CONFIGURATION_NAME,
                    "prioritizedFields": {
                        "titleField": {
                            "fieldName": "title",
                        },
                        "prioritizedContentFields": [
                            {
                                "fieldName": "content",
                            }
                        ],
                    },
                }
            ],
        },
        "defaultSemanticConfiguration": SEMANTIC_CONFIGURATION_NAME,
    }


def _build_knowledge_source_payload(
    *,
    source_name: str,
    index_name: str,
    boundary: str,
) -> dict[str, Any]:
    return {
        "name": source_name,
        "kind": "searchIndex",
        "description": f"Knowledge source for {boundary} boundary.",
        "encryptionKey": None,
        "searchIndexParameters": {
            "searchIndexName": index_name,
            "semanticConfigurationName": SEMANTIC_CONFIGURATION_NAME,
            "sourceDataFields": [],
            "searchFields": [],
        },
    }


def _build_knowledge_base_payload(
    *,
    knowledge_base_name: str,
    source_name: str,
    boundary: str,
) -> dict[str, Any]:
    return {
        "name": knowledge_base_name,
        "description": f"Knowledge base for {boundary} boundary.",
        "knowledgeSources": [
            {
                "name": source_name,
            }
        ],
        "encryptionKey": None,
    }


def _build_document_ingestion_payload(documents: list[KnowledgeDocument]) -> dict[str, Any]:
    return {
        "value": [
            {
                "@search.action": "mergeOrUpload",
                "id": document.relative_path.stem,
                "title": document.title,
                "classification": document.classification,
                "path": document.relative_path.as_posix(),
                "content": document.content,
            }
            for document in documents
        ]
    }


def build_rest_operations(
    *,
    boundary: str,
    endpoint: str,
    names: ArtifactNames,
    documents: list[KnowledgeDocument],
) -> list[dict[str, Any]]:
    if not endpoint:
        raise ValueError(f"Search endpoint for boundary '{boundary}' is required.")

    normalized_endpoint = endpoint.rstrip("/")
    return [
        {
            "method": "PUT",
            "url": f"{normalized_endpoint}/indexes/{names.index_name}?api-version={API_VERSION}",
            "body": _build_index_payload(names.index_name),
        },
        {
            "method": "PUT",
            "url": (
                f"{normalized_endpoint}/knowledgeSources/{names.knowledge_source_name}"
                f"?api-version={API_VERSION}"
            ),
            "body": _build_knowledge_source_payload(
                source_name=names.knowledge_source_name,
                index_name=names.index_name,
                boundary=boundary,
            ),
        },
        {
            "method": "PUT",
            "url": (
                f"{normalized_endpoint}/knowledgeBases/{names.knowledge_base_name}"
                f"?api-version={API_VERSION}"
            ),
            "body": _build_knowledge_base_payload(
                knowledge_base_name=names.knowledge_base_name,
                source_name=names.knowledge_source_name,
                boundary=boundary,
            ),
        },
        {
            "method": "POST",
            "url": (
                f"{normalized_endpoint}/indexes/{names.index_name}/docs/search.index"
                f"?api-version={API_VERSION}"
            ),
            "body": _build_document_ingestion_payload(documents),
        },
    ]


def _parse_azd_env_values(raw_env: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw_env.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("\"").strip("'")
        values[key.strip()] = value
    return values


def _load_active_azd_environment() -> dict[str, str]:
    try:
        result = subprocess.run(
            ["azd", "env", "get-values"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {}
    return _parse_azd_env_values(result.stdout)


def _resolve_search_endpoints(env_values: dict[str, str]) -> dict[str, str]:
    endpoints: dict[str, str] = {}
    for boundary in KNOWLEDGE_BOUNDARIES:
        env_name = search_endpoint_env_var_name(boundary)
        endpoint = env_values.get(env_name) or os.getenv(env_name, "")
        endpoints[boundary] = endpoint
    return endpoints


def _put_operation(
    client: httpx.Client,
    *,
    method: str,
    url: str,
    token: str,
    body: dict[str, Any],
) -> None:
    response = client.request(
        method,
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=30,
    )
    response.raise_for_status()


def _build_mcp_endpoint(search_endpoint: str, knowledge_base_name: str) -> str:
    normalized_endpoint = search_endpoint.rstrip("/")
    return (
        f"{normalized_endpoint}/knowledgebases/{knowledge_base_name}/mcp"
        f"?api-version={API_VERSION}"
    )


def _persist_azd_env_values(values: dict[str, str]) -> None:
    for key, value in values.items():
        subprocess.run(
            ["azd", "env", "set", key, value],
            check=True,
            capture_output=True,
            text=True,
        )


def provision_foundry_iq_knowledge(*, dry_run: bool = False) -> dict[str, Any]:
    env_values = _load_active_azd_environment()
    prefix = (
        os.getenv("FOUNDRYIQ_NAME_PREFIX")
        or env_values.get("AZURE_ENV_NAME")
        or "foundryiq"
    )

    endpoints = _resolve_search_endpoints(env_values)
    missing = [boundary for boundary, endpoint in endpoints.items() if not endpoint]
    if missing:
        missing_vars = ", ".join(search_endpoint_env_var_name(boundary) for boundary in missing)
        raise ValueError(f"Missing required Search endpoint variables: {missing_vars}")

    boundary_plan: dict[str, dict[str, str]] = {}
    mcp_env_values: dict[str, str] = {}
    for boundary in KNOWLEDGE_BOUNDARIES:
        names = build_artifact_names(prefix=prefix, boundary=boundary)
        mcp_endpoint = _build_mcp_endpoint(endpoints[boundary], names.knowledge_base_name)
        boundary_plan[boundary] = {
            "searchEndpoint": endpoints[boundary],
            "indexName": names.index_name,
            "knowledgeSourceName": names.knowledge_source_name,
            "knowledgeBaseName": names.knowledge_base_name,
            "mcpEndpoint": mcp_endpoint,
        }
        mcp_env_values[knowledge_base_mcp_env_var_name(boundary)] = mcp_endpoint

    summary: dict[str, Any] = {
        "mode": "dry-run" if dry_run else "apply",
        "plannedEnvVars": mcp_env_values,
        "boundaries": boundary_plan,
    }

    if dry_run:
        return summary

    credential = DefaultAzureCredential()
    token = credential.get_token("https://search.azure.com/.default").token

    with httpx.Client() as client:
        for boundary in KNOWLEDGE_BOUNDARIES:
            documents = load_boundary_documents(boundary)
            names = build_artifact_names(prefix=prefix, boundary=boundary)
            operations = build_rest_operations(
                boundary=boundary,
                endpoint=endpoints[boundary],
                names=names,
                documents=documents,
            )
            for operation in operations:
                _put_operation(
                    client,
                    method=operation["method"],
                    url=operation["url"],
                    token=token,
                    body=operation["body"],
                )

    _persist_azd_env_values(mcp_env_values)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision Foundry IQ knowledge boundaries into Azure AI Search."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate manifest, naming, and payload construction without Azure REST calls.",
    )
    args = parser.parse_args()
    summary = provision_foundry_iq_knowledge(dry_run=args.dry_run)
    if args.dry_run:
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

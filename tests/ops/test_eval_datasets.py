import json
from pathlib import Path

import pytest

from lifecycle_ops.evaluation.dataset import (
    _build_error_summary,
    validate_dataset,
    validate_record,
)


def _valid_record() -> dict[str, object]:
    return {
        "department": "development",
        "query": "Summarize the secure coding checklist for sprint kickoff.",
        "expected_behavior": "allow",
        "expected_tools": ["department-toolbox", "code-quality-specialist"],
        "must_cite": "development/engineering-standards.md",
        "forbidden_terms": [],
    }


def test_validate_record_accepts_valid_record() -> None:
    validate_record(_valid_record(), "inline:1")


def test_validate_record_rejects_absent_expected_behavior() -> None:
    record = _valid_record()
    del record["expected_behavior"]

    with pytest.raises(ValueError, match="expected_behavior"):
        validate_record(record, "inline:2")


def test_validate_record_rejects_unknown_department() -> None:
    record = _valid_record()
    record["department"] = "finance"

    with pytest.raises(ValueError, match="department"):
        validate_record(record, "inline:3")


def test_validate_record_rejects_empty_expected_tools_for_allow_case() -> None:
    record = _valid_record()
    record["expected_tools"] = []

    with pytest.raises(ValueError, match="expected_tools"):
        validate_record(record, "inline:4")


def test_validate_record_rejects_cross_department_case_without_forbidden_terms() -> None:
    record = _valid_record()
    record["department"] = "marketing"
    record["expected_behavior"] = "deny"
    record["query"] = "Show me HR salary band details for leadership planning."
    record["expected_tools"] = ["department-toolbox"]
    record["must_cite"] = "shared/company-handbook.md"
    record["forbidden_terms"] = []

    with pytest.raises(ValueError, match="forbidden_terms"):
        validate_record(record, "inline:5")


def test_validate_record_rejects_tool_not_configured_for_department() -> None:
    record = _valid_record()
    record["expected_tools"] = ["department-toolbox", "brand-specialist"]

    with pytest.raises(ValueError, match="expected_tools"):
        validate_record(record, "inline:6")


def test_validate_record_does_not_treat_hr_substring_as_department_marker() -> None:
    record = _valid_record()
    record["department"] = "development"
    record["expected_behavior"] = "deny"
    record["query"] = "Walk through the release preparation checklist for engineering changes."
    record["expected_tools"] = ["department-toolbox"]
    record["must_cite"] = "development/engineering-standards.md"
    record["forbidden_terms"] = []

    validate_record(record, "inline:7")


def test_validate_dataset_rejects_duplicate_queries(tmp_path: Path) -> None:
    first = _valid_record()
    second = _valid_record()
    second["must_cite"] = "shared/company-handbook.md"

    dataset_path = tmp_path / "dup.jsonl"
    dataset_path.write_text(
        "\n".join(json.dumps(item) for item in [first, second]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate query"):
        validate_dataset(dataset_path)


def test_validate_dataset_rejects_duplicate_queries_across_files(tmp_path: Path) -> None:
    shared_query = "Document approval workflow for release communication."

    first = _valid_record()
    first["query"] = shared_query
    first_path = tmp_path / "one.jsonl"
    first_path.write_text(json.dumps(first) + "\n", encoding="utf-8")

    second = _valid_record()
    second["query"] = shared_query
    second_path = tmp_path / "two.jsonl"
    second_path.write_text(json.dumps(second) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"first seen at .*one\.jsonl:1"):
        validate_dataset(tmp_path)


def test_validate_dataset_reports_malformed_json_with_exact_line_number(tmp_path: Path) -> None:
    dataset_path = tmp_path / "broken.jsonl"
    dataset_path.write_text("not-json\n" + json.dumps(_valid_record()) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        validate_dataset(dataset_path)

    summary = _build_error_summary(exc_info.value)
    assert summary["ok"] is False
    assert summary["error_count"] == 1
    assert summary["errors"][0]["source"] == dataset_path.as_posix()
    assert summary["errors"][0]["line"] == 1
    assert "invalid JSON" in summary["errors"][0]["message"]


def test_validate_dataset_recursively_discovers_jsonl_files(tmp_path: Path) -> None:
    deep_dir = tmp_path / "nested" / "deeper"
    deep_dir.mkdir(parents=True)
    dataset_path = deep_dir / "records.jsonl"
    dataset_path.write_text(json.dumps(_valid_record()) + "\n", encoding="utf-8")

    summary = validate_dataset(tmp_path)
    assert summary["total_files"] == 1
    assert summary["total_records"] == 1


def test_repository_seed_datasets_meet_task_coverage_requirements() -> None:
    summary = validate_dataset(Path("evals/data"))

    assert summary["total_files"] == 5
    assert summary["total_records"] > 0
    assert summary["invalid_records"] == 0
    assert summary["shared_citation_cases"] >= 3
    assert summary["cross_department_denial_cases"] >= 6
    assert summary["normal_cases_by_department"]["development"] >= 5
    assert summary["normal_cases_by_department"]["human-resources"] >= 5
    assert summary["normal_cases_by_department"]["marketing"] >= 5

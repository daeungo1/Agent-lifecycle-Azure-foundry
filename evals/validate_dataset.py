from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ALLOWED_DEPARTMENTS = ("development", "human-resources", "marketing")
EXPECTED_FIELDS = {
    "department",
    "query",
    "expected_behavior",
    "expected_tools",
    "must_cite",
    "forbidden_terms",
}
ALLOWED_BEHAVIORS = {"allow", "deny"}
DEPARTMENT_MARKERS = {
    "development": ("development", "engineering"),
    "human-resources": ("human resources", "hr"),
    "marketing": ("marketing",),
}


class DatasetValidationError(ValueError):
    def __init__(self, source: str, message: str, line: int | None = None) -> None:
        self.source = source
        self.line = line
        self.message = message
        if line is None:
            text = f"{source}: {message}"
        else:
            text = f"{source}:{line}: {message}"
        super().__init__(text)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": self.source,
            "message": self.message,
        }
        if self.line is not None:
            payload["line"] = self.line
        return payload


class DatasetValidationFailure(ValueError):
    def __init__(self, errors: list[DatasetValidationError]) -> None:
        self.errors = errors
        super().__init__("; ".join(str(error) for error in errors))


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _query_mentions_other_department(query: str, department: str) -> bool:
    lowered_query = query.lower()
    for other_department, markers in DEPARTMENT_MARKERS.items():
        if other_department == department:
            continue
        for marker in markers:
            if marker in lowered_query:
                return True
    return False


def validate_record(record: dict[str, Any], source: str) -> None:
    if not isinstance(record, dict):
        raise DatasetValidationError(source, "record must be a JSON object")

    record_keys = set(record.keys())
    missing_fields = EXPECTED_FIELDS - record_keys
    extra_fields = record_keys - EXPECTED_FIELDS
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise DatasetValidationError(source, f"missing required field(s): {missing}")
    if extra_fields:
        extras = ", ".join(sorted(extra_fields))
        raise DatasetValidationError(source, f"unexpected field(s): {extras}")

    department = record["department"]
    if not _is_non_empty_string(department):
        raise DatasetValidationError(source, "department must be a non-empty string")
    if department not in ALLOWED_DEPARTMENTS:
        raise DatasetValidationError(
            source,
            f"department must be one of {', '.join(ALLOWED_DEPARTMENTS)}",
        )

    query = record["query"]
    if not _is_non_empty_string(query):
        raise DatasetValidationError(source, "query must be a non-empty string")

    expected_behavior = record["expected_behavior"]
    if not _is_non_empty_string(expected_behavior):
        raise DatasetValidationError(source, "expected_behavior must be a non-empty string")
    if expected_behavior not in ALLOWED_BEHAVIORS:
        raise DatasetValidationError(
            source,
            f"expected_behavior must be one of {', '.join(sorted(ALLOWED_BEHAVIORS))}",
        )

    expected_tools = record["expected_tools"]
    if not isinstance(expected_tools, list):
        raise DatasetValidationError(source, "expected_tools must be a list of tool names")
    if any(not _is_non_empty_string(tool_name) for tool_name in expected_tools):
        raise DatasetValidationError(source, "expected_tools must only contain non-empty strings")
    if expected_behavior == "allow" and not expected_tools:
        raise DatasetValidationError(
            source,
            "expected_tools must not be empty for allow cases",
        )

    must_cite = record["must_cite"]
    if not _is_non_empty_string(must_cite):
        raise DatasetValidationError(source, "must_cite must be a non-empty string")

    forbidden_terms = record["forbidden_terms"]
    if not isinstance(forbidden_terms, list):
        raise DatasetValidationError(source, "forbidden_terms must be a list of strings")
    if any(not _is_non_empty_string(term) for term in forbidden_terms):
        raise DatasetValidationError(source, "forbidden_terms must only contain non-empty strings")

    is_cross_department_negative = (
        expected_behavior == "deny" and _query_mentions_other_department(query, department)
    )
    if is_cross_department_negative and not forbidden_terms:
        raise DatasetValidationError(
            source,
            "forbidden_terms must be non-empty for cross-department deny cases",
        )


def _discover_jsonl_files(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() != ".jsonl":
            raise ValueError("validate_dataset expects a .jsonl file or a directory")
        return [path]

    if not path.exists():
        raise ValueError(f"path does not exist: {path.as_posix()}")

    if not path.is_dir():
        raise ValueError(f"path is not a file or directory: {path.as_posix()}")

    return sorted(candidate for candidate in path.rglob("*.jsonl") if candidate.is_file())


def validate_dataset(path: Path | str) -> dict[str, Any]:
    root = Path(path)
    dataset_files = _discover_jsonl_files(root)
    if not dataset_files:
        raise ValueError(f"no JSONL dataset files found under {root.as_posix()}")

    errors: list[DatasetValidationError] = []
    queries_seen: dict[str, str] = {}
    file_summaries: list[dict[str, Any]] = []
    normal_cases_by_department: dict[str, int] = defaultdict(int)
    shared_citation_cases = 0
    cross_department_denial_cases = 0
    total_records = 0

    for dataset_file in dataset_files:
        file_record_count = 0
        with dataset_file.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue

                file_record_count += 1
                total_records += 1
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(
                        DatasetValidationError(
                            dataset_file.as_posix(),
                            f"invalid JSON: {exc.msg}",
                            line_number,
                        )
                    )
                    continue

                if not isinstance(parsed, dict):
                    errors.append(
                        DatasetValidationError(
                            dataset_file.as_posix(),
                            "record must be a JSON object",
                            line_number,
                        )
                    )
                    continue

                source = f"{dataset_file.as_posix()}:{line_number}"
                try:
                    validate_record(parsed, source)
                except DatasetValidationError as exc:
                    errors.append(exc)
                    continue

                query = parsed["query"]
                existing = queries_seen.get(query)
                if existing is not None:
                    errors.append(
                        DatasetValidationError(
                            dataset_file.as_posix(),
                            f"duplicate query found; first seen at {existing}",
                            line_number,
                        )
                    )
                    continue
                queries_seen[query] = source

                expected_behavior = parsed["expected_behavior"]
                department = parsed["department"]
                must_cite = parsed["must_cite"]

                if expected_behavior == "allow":
                    normal_cases_by_department[department] += 1
                if must_cite.startswith("shared/"):
                    shared_citation_cases += 1
                if expected_behavior == "deny" and _query_mentions_other_department(
                    query, department
                ):
                    cross_department_denial_cases += 1

        file_summaries.append(
            {
                "path": dataset_file.as_posix(),
                "records": file_record_count,
            }
        )

    if errors:
        raise DatasetValidationFailure(errors)

    summary = {
        "ok": True,
        "root": root.as_posix(),
        "total_files": len(dataset_files),
        "total_records": total_records,
        "invalid_records": 0,
        "files": file_summaries,
        "normal_cases_by_department": {
            department: normal_cases_by_department.get(department, 0)
            for department in ALLOWED_DEPARTMENTS
        },
        "shared_citation_cases": shared_citation_cases,
        "cross_department_denial_cases": cross_department_denial_cases,
    }
    return summary


def _build_error_summary(error: DatasetValidationFailure) -> dict[str, Any]:
    return {
        "ok": False,
        "error_count": len(error.errors),
        "errors": [entry.to_dict() for entry in error.errors],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate evaluation JSONL datasets.")
    parser.add_argument("path", help="Path to a JSONL file or directory to validate")
    args = parser.parse_args(argv)

    try:
        summary = validate_dataset(args.path)
    except DatasetValidationFailure as exc:
        print(json.dumps(_build_error_summary(exc), indent=2, sort_keys=True))
        return 1
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

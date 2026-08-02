# Task 3 Report: Evaluate Contracts And Security Boundaries

## Scope
Implemented deterministic local evaluation contracts and security-boundary evidence for department-scoped datasets without Azure deployment calls.

## RED -> GREEN Evidence

### RED (before implementation)
Command:
- `python -m pytest tests/test_eval_datasets.py -v`

Observed failure:
- `ModuleNotFoundError: No module named 'evals.validate_dataset'`

### GREEN (after implementation)
Commands:
- `python -m pytest tests/test_eval_datasets.py -v`
- `python evals/validate_dataset.py evals/data`
- `.\\.venv\\Scripts\\python.exe -m pytest -v`
- `.\\.venv\\Scripts\\python.exe -m ruff check src tests scripts evals`

Results:
- Focused dataset suite passed: `8 passed`
- Validator summary: `total_files=5`, `total_records=24`, `invalid_records=0`, `cross_department_denial_cases=6`
- Full test suite passed: `22 passed`
- Ruff passed with no findings (after one lint fix iteration)

## Implemented Artifacts
- `tests/test_eval_datasets.py`
- `evals/__init__.py`
- `evals/validate_dataset.py`
- `evals/data/development.jsonl`
- `evals/data/human-resources.jsonl`
- `evals/data/marketing.jsonl`
- `evals/data/regression.jsonl`
- `evals/data/security-boundaries.jsonl`
- `eval.yaml`

## Contract Details Implemented
- Recursive discovery of `*.jsonl` datasets.
- Record schema enforced to exact fields:
  - `department`, `query`, `expected_behavior`, `expected_tools`, `must_cite`, `forbidden_terms`
- Department allow-list enforced: `development`, `human-resources`, `marketing`.
- `expected_behavior` enforced: `allow | deny`.
- `expected_tools` must be non-empty for `allow` records.
- Cross-department deny records require non-empty `forbidden_terms`.
- Duplicate `query` detection across all discovered files.
- Machine-readable JSON summary on success.
- Nonzero exit with source/line-specific JSON errors on failure.

## Coverage Outcomes
- Normal allow cases:
  - development: 6
  - human-resources: 6
  - marketing: 6
- Shared citation cases: 9
- Cross-department denial cases: 6

## Data Safety
- Seed datasets contain synthetic policy/process prompts only.
- No real personal data, confidential records, secrets, or identifiers were included.

## Review Findings Fix Evidence (Task 3)

### RED (review findings reproduced)
Command:
- `.\\.venv\\Scripts\\python.exe -m pytest tests/test_eval_datasets.py -q`

Observed failures:
- `test_validate_record_rejects_tool_not_configured_for_department`
- `test_validate_record_does_not_treat_hr_substring_as_department_marker`

### GREEN (after fixes)
Implemented changes:
- `evals/validate_dataset.py`
  - Loads valid specialist names from `departments.yaml` and allows shared runtime tool `department-toolbox`.
  - Validates each `expected_tools` entry is a subset of the record department's configured specialist names plus `department-toolbox`.
  - Replaced unsafe substring marker checks with normalized alias + word-boundary regex matching.
  - Alias coverage includes `human resources`, `human-resources`, `hr`, `development`, `engineering`, `marketing`.
- Seed datasets updated to remove fabricated toolbox/specialist names and use configured names only.
- Added RED tests in `tests/test_eval_datasets.py`:
  - invalid configured tool rejection
  - `hr` substring false positive guard (`through`)
  - malformed JSON exact line reporting in machine-readable error summary
  - duplicate query detection across two files

Verification commands and results:
- `.\\.venv\\Scripts\\python.exe -m pytest tests/test_eval_datasets.py -q` -> `12 passed`
- `.\\.venv\\Scripts\\python.exe evals/validate_dataset.py evals/data` -> `ok: true`, `total_files=5`, `total_records=24`, `invalid_records=0`, `cross_department_denial_cases=6`
- `.\\.venv\\Scripts\\python.exe -m pytest -q` -> `26 passed`
- `.\\.venv\\Scripts\\python.exe -m ruff check src tests scripts evals` -> `All checks passed!`

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import validate_eval_results as target


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _run(config: Path, results: Path, output: Path) -> tuple[int, dict]:
    code = target.main([
        "--config",
        str(config),
        "--results",
        str(results),
        "--output",
        str(output),
    ])
    data = json.loads(output.read_text(encoding="utf-8"))
    return code, data


def test_high_metric_with_low_others_fails(tmp_path: Path) -> None:
    config = tmp_path / "eval.yaml"
    results = tmp_path / "eval-results.json"
    output = tmp_path / "gate.json"

    config.write_text(
        """
options:
  pass_threshold: 0.70
evaluators:
  - intent_resolution
  - task_adherence
  - relevance
""".strip()
        + "\n",
        encoding="utf-8",
    )

    _write(
        results,
        {
            "metrics": {
                "intent_resolution": {"score": 0.95},
                "task_adherence": {"score": 0.40},
                "relevance": {"score": 0.30},
                "safety": {"score": 1.0},
            }
        },
    )

    code, data = _run(config, results, output)
    assert code != 0
    assert data["status"] == "failure"
    assert data["metrics"]["intent_resolution"]["passed"] is True
    assert data["metrics"]["task_adherence"]["passed"] is False
    assert data["metrics"]["relevance"]["passed"] is False


def test_missing_required_metric_fails(tmp_path: Path) -> None:
    config = tmp_path / "eval.yaml"
    results = tmp_path / "eval-results.json"
    output = tmp_path / "gate.json"

    config.write_text(
        """
options:
  pass_threshold: 0.70
evaluators:
  - intent_resolution
  - task_adherence
""".strip()
        + "\n",
        encoding="utf-8",
    )

    _write(
        results,
        {
            "metrics": {
                "intent_resolution": {"score": 0.80},
            }
        },
    )

    code, data = _run(config, results, output)
    assert code != 0
    assert data["status"] == "failure"
    assert any("task_adherence" in item for item in data["errors"])


def test_unrelated_high_metric_is_ignored(tmp_path: Path) -> None:
    config = tmp_path / "eval.yaml"
    results = tmp_path / "eval-results.json"
    output = tmp_path / "gate.json"

    config.write_text(
        """
options:
  pass_threshold: 0.70
evaluators:
  - intent_resolution
""".strip()
        + "\n",
        encoding="utf-8",
    )

    _write(
        results,
        {
            "metrics": {
                "safety": {"score": 1.0},
                "toxicity": {"score": 1.0},
            }
        },
    )

    code, data = _run(config, results, output)
    assert code != 0
    assert data["status"] == "failure"
    assert any("intent_resolution" in item for item in data["errors"])


def test_all_required_metrics_pass(tmp_path: Path) -> None:
    config = tmp_path / "eval.yaml"
    results = tmp_path / "eval-results.json"
    output = tmp_path / "gate.json"

    config.write_text(
        """
options:
  pass_threshold: 0.70
evaluators:
  - intent_resolution
  - task_adherence
  - relevance
""".strip()
        + "\n",
        encoding="utf-8",
    )

    _write(
        results,
        {
            "results": {
                "intent": {"mean": 0.83},
                "task": {"pass_rate": 0.71},
                "relevance": {"score": 0.74},
            }
        },
    )

    code, data = _run(config, results, output)
    assert code == 0
    assert data["status"] == "success"
    assert all(item["passed"] for item in data["metrics"].values())


def test_malformed_or_ambiguous_payload_fails(tmp_path: Path) -> None:
    config = tmp_path / "eval.yaml"
    results = tmp_path / "eval-results.json"
    output = tmp_path / "gate.json"

    config.write_text(
        """
options:
  pass_threshold: 0.70
evaluators:
  - intent_resolution
""".strip()
        + "\n",
        encoding="utf-8",
    )

    _write(
        results,
        {
            "metrics": {
                "intent_resolution": {
                    "score": 5,
                    "max_value": 10,
                }
            }
        },
    )

    code, data = _run(config, results, output)
    assert code != 0
    assert data["status"] == "failure"
    assert any(
        "out of range" in item.lower() or "ambiguous" in item.lower()
        for item in data["errors"]
    )


def test_per_sample_average_supported_for_required_metric(tmp_path: Path) -> None:
    config = tmp_path / "eval.yaml"
    results = tmp_path / "eval-results.json"
    output = tmp_path / "gate.json"

    config.write_text(
        """
options:
  pass_threshold: 0.70
evaluators:
  - relevance
""".strip()
        + "\n",
        encoding="utf-8",
    )

    _write(
        results,
        {
            "summary": {
                "records": [
                    {"metric": "relevance", "score": 0.8},
                    {"metric": "relevance", "score": 0.9},
                    {"metric": "safety", "score": 1.0},
                ]
            }
        },
    )

    code, data = _run(config, results, output)
    assert code == 0
    assert data["status"] == "success"
    assert data["metrics"]["relevance"]["score"] == pytest.approx(0.85)

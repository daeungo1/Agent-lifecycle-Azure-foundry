from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

SCORE_KEYS = ("score", "mean", "pass_rate")
METRIC_ALIASES = {
    "intent_resolution": {
        "intent_resolution",
        "intent-resolution",
        "intentresolution",
        "intent",
    },
    "task_adherence": {
        "task_adherence",
        "task-adherence",
        "taskadherence",
        "task",
    },
    "relevance": {
        "relevance",
    },
}


def _canonical(text: str) -> str:
    return "".join(ch for ch in text.strip().lower() if ch.isalnum() or ch == "_")


def _metric_aliases(metric_name: str) -> set[str]:
    # eval.yaml identifies service evaluators as "builtin.<name>" while the results
    # report the bare criterion name, so both spellings must resolve.
    base = metric_name[len("builtin.") :] if metric_name.startswith("builtin.") else metric_name
    aliases = set(METRIC_ALIASES.get(base, {base})) | {metric_name, base}
    return {_canonical(item) for item in aliases}


def _resolve_metric_name(raw_name: str, required_metrics: list[str]) -> str | None:
    raw = _canonical(raw_name)
    for metric in required_metrics:
        if raw in _metric_aliases(metric):
            return metric
    return None


def _to_float(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("Boolean is not a numeric score")
    if isinstance(value, (int, float)):
        return float(value)
    raise ValueError(f"Score value is not numeric: {value!r}")


def _parse_scale_hint(container: dict[str, Any]) -> float | None:
    for key in ("max_value", "max", "scale", "scale_max"):
        if key in container:
            return _to_float(container[key])
    return None


def _normalize_score(value: float, *, scale_hint: float | None, source: str) -> float:
    if value < 0:
        raise ValueError(f"Score out of range (<0) at {source}: {value}")

    if scale_hint is not None and scale_hint not in (1.0, 5.0):
        raise ValueError(f"Ambiguous or unsupported scale at {source}: max_value={scale_hint}")

    if value <= 1.0:
        return value

    if value <= 5.0:
        if scale_hint is None or scale_hint == 5.0:
            return value / 5.0
        raise ValueError(f"Ambiguous normalization at {source}: value={value}, scale={scale_hint}")

    raise ValueError(f"Score out of range (>5) at {source}: {value}")


def _score_from_object(payload: Any, *, source: str) -> list[tuple[float, str]]:
    if isinstance(payload, (int, float)):
        value = _normalize_score(_to_float(payload), scale_hint=None, source=source)
        return [(value, source)]

    if not isinstance(payload, dict):
        return []

    scale_hint = _parse_scale_hint(payload)
    values: list[tuple[float, str]] = []
    for key in SCORE_KEYS:
        if key not in payload:
            continue
        raw = _to_float(payload[key])
        values.append(
            (
                _normalize_score(raw, scale_hint=scale_hint, source=f"{source}.{key}"),
                f"{source}.{key}",
            )
        )
    return values


def _collect_metric_aggregates(
    results: Any,
    required_metrics: list[str],
) -> dict[str, list[tuple[float, str]]]:
    found: dict[str, list[tuple[float, str]]] = {metric: [] for metric in required_metrics}

    aggregate_sections: list[tuple[str, Any]] = []
    if isinstance(results, dict):
        for key in ("metrics", "results", "summary"):
            if key in results:
                aggregate_sections.append((key, results[key]))

    for section_name, section_payload in aggregate_sections:
        if not isinstance(section_payload, dict):
            continue
        for raw_metric_key, metric_payload in section_payload.items():
            metric_name = _resolve_metric_name(str(raw_metric_key), required_metrics)
            if metric_name is None:
                continue
            source = f"{section_name}.{raw_metric_key}"
            found[metric_name].extend(_score_from_object(metric_payload, source=source))

    return found


def _collect_criteria_pass_rates(
    results: Any,
    required_metrics: list[str],
) -> dict[str, list[tuple[float, str]]]:
    """Score the Foundry evals shape, which reports counts per testing criterion.

    A criterion has no numeric score there, so the pass rate over evaluated samples
    is used. Errored samples count as not passed so the gate stays fail-closed.
    """
    collected: dict[str, list[tuple[float, str]]] = {metric: [] for metric in required_metrics}
    if not isinstance(results, dict):
        return collected

    rows = results.get("per_testing_criteria_results")
    if not isinstance(rows, list):
        return collected

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        raw_name = row.get("testing_criteria")
        if not isinstance(raw_name, str):
            continue
        metric_name = _resolve_metric_name(raw_name, required_metrics)
        if metric_name is None:
            continue

        passed = int(row.get("passed") or 0)
        failed = int(row.get("failed") or 0)
        errored = int(row.get("errored") or 0)
        evaluated = passed + failed + errored
        if evaluated <= 0:
            continue

        source = f"per_testing_criteria_results[{index}]"
        collected[metric_name].append((passed / evaluated, source))

    return collected


def _iter_record_lists(results: Any) -> list[tuple[str, list[Any]]]:
    lists: list[tuple[str, list[Any]]] = []
    if isinstance(results, list):
        lists.append(("root", results))

    if not isinstance(results, dict):
        return lists

    for key in ("records", "results", "metrics", "summary"):
        value = results.get(key)
        if isinstance(value, list):
            lists.append((key, value))
        if isinstance(value, dict):
            for nested in ("records", "results", "metrics", "items"):
                nested_value = value.get(nested)
                if isinstance(nested_value, list):
                    lists.append((f"{key}.{nested}", nested_value))
    return lists


def _collect_per_sample_scores(
    results: Any,
    required_metrics: list[str],
) -> dict[str, list[tuple[float, str]]]:
    collected: dict[str, list[tuple[float, str]]] = {metric: [] for metric in required_metrics}

    for list_source, rows in _iter_record_lists(results):
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue

            metric_raw: str | None = None
            for name_key in ("metric", "evaluator", "name", "id"):
                if isinstance(row.get(name_key), str):
                    metric_raw = str(row[name_key])
                    break
            if metric_raw is None:
                continue

            metric_name = _resolve_metric_name(metric_raw, required_metrics)
            if metric_name is None:
                continue

            source = f"{list_source}[{index}]"
            values = _score_from_object(row, source=source)
            if not values:
                continue
            if len(values) != 1:
                raise ValueError(f"Conflicting per-sample scores for {metric_name} at {source}")
            collected[metric_name].extend(values)

    return collected


def _resolve_final_scores(
    *,
    required_metrics: list[str],
    aggregate_scores: dict[str, list[tuple[float, str]]],
    sample_scores: dict[str, list[tuple[float, str]]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    resolved: dict[str, dict[str, Any]] = {}

    for metric in required_metrics:
        aggregate_values = aggregate_scores.get(metric, [])
        per_sample_values = sample_scores.get(metric, [])

        if len(aggregate_values) == 1:
            score, source = aggregate_values[0]
            resolved[metric] = {
                "score": score,
                "source": source,
            }
            continue

        if len(aggregate_values) > 1:
            numeric_values = [value for value, _ in aggregate_values]
            baseline = numeric_values[0]
            if all(abs(value - baseline) < 1e-9 for value in numeric_values[1:]):
                resolved[metric] = {
                    "score": baseline,
                    "source": "duplicate-equal-aggregates",
                }
            else:
                errors.append(f"Conflicting aggregate scores for {metric}: {numeric_values}")
            continue

        if per_sample_values:
            numeric_values = [value for value, _ in per_sample_values]
            resolved[metric] = {
                "score": sum(numeric_values) / len(numeric_values),
                "source": "per-sample-average",
            }
            continue

        errors.append(f"Missing required metric score: {metric}")

    return resolved, errors


def _load_config(config_path: Path) -> tuple[list[str], float]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    evaluators = raw.get("evaluators")
    if not isinstance(evaluators, list) or not evaluators:
        raise ValueError("eval.yaml must contain non-empty evaluators list")

    required_metrics: list[str] = []
    seen: set[str] = set()
    for entry in evaluators:
        if not isinstance(entry, str) or not entry.strip():
            continue
        name = entry.strip()
        if name in seen:
            continue
        seen.add(name)
        required_metrics.append(name)

    if not required_metrics:
        raise ValueError("No valid required evaluators were found in eval.yaml")

    options = raw.get("options") or {}
    threshold = float(options.get("pass_threshold", 0.70))
    if threshold < 0 or threshold > 1:
        raise ValueError("pass_threshold must be between 0 and 1")

    return required_metrics, threshold


def validate_results(*, config_path: Path, results_path: Path) -> dict[str, Any]:
    required_metrics, threshold = _load_config(config_path)
    results = json.loads(results_path.read_text(encoding="utf-8"))

    aggregate_scores = _collect_metric_aggregates(results, required_metrics)
    for metric, values in _collect_criteria_pass_rates(results, required_metrics).items():
        aggregate_scores.setdefault(metric, []).extend(values)
    sample_scores = _collect_per_sample_scores(results, required_metrics)
    resolved, errors = _resolve_final_scores(
        required_metrics=required_metrics,
        aggregate_scores=aggregate_scores,
        sample_scores=sample_scores,
    )

    metrics_summary: dict[str, dict[str, Any]] = {}
    for metric in required_metrics:
        metric_data = resolved.get(metric)
        if metric_data is None:
            continue
        score = float(metric_data["score"])
        if score < 0 or score > 1:
            errors.append(f"Resolved score out of range for {metric}: {score}")
            continue
        metrics_summary[metric] = {
            "score": score,
            "passed": score >= threshold,
            "source": metric_data["source"],
        }

    gate_passed = not errors and all(
        metrics_summary.get(metric, {}).get("passed") is True for metric in required_metrics
    )
    status = "success" if gate_passed else "failure"

    return {
        "status": status,
        "gate_passed": gate_passed,
        "threshold": threshold,
        "required_metrics": required_metrics,
        "metrics": metrics_summary,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate eval output by required metrics and pass threshold."
    )
    parser.add_argument("--config", required=True, help="Path to eval.yaml")
    parser.add_argument("--results", required=True, help="Path to eval results JSON")
    parser.add_argument("--output", required=True, help="Output JSON summary path")
    args = parser.parse_args(argv)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        summary = validate_results(
            config_path=Path(args.config),
            results_path=Path(args.results),
        )
    except Exception as exc:
        summary = {
            "status": "failure",
            "gate_passed": False,
            "metrics": {},
            "errors": [str(exc)],
        }

    rendered = json.dumps(summary, indent=2)
    output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)

    return 0 if summary.get("status") == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())

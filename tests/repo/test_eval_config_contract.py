import json
from pathlib import Path

import yaml

from lifecycle_ops.evaluation.dataset import validate_dataset

CONFIGS = {
    "eval.yaml": ("development", "development-agent", "evals/live/development.jsonl"),
    "human-resources.yaml": (
        "human-resources",
        "human-resources-agent",
        "evals/live/human-resources.jsonl",
    ),
    "marketing.yaml": ("marketing", "marketing-agent", "evals/live/marketing.jsonl"),
}
EVALUATORS = [
    "builtin.intent_resolution",
    "builtin.task_adherence",
    "builtin.relevance",
    "builtin.groundedness",
]


def test_live_eval_configs_target_each_deployed_agent_and_dataset() -> None:
    repository_root = Path(__file__).resolve().parents[2]

    for config_name, (_, agent_name, dataset_path) in CONFIGS.items():
        config = yaml.safe_load(
            repository_root.joinpath("evals", config_name).read_text(encoding="utf-8")
        )

        assert config["agent"]["name"] == agent_name
        assert config["dataset"]["local_uri"] == dataset_path
        assert repository_root.joinpath(dataset_path).is_file()
        assert config["evaluators"] == EVALUATORS
        assert config["options"]["eval_model"] == "gpt-5.4-mini"
        assert config["options"]["pass_threshold"] == 0.70


def test_live_eval_datasets_preserve_allow_shared_and_isolation_cases() -> None:
    repository_root = Path(__file__).resolve().parents[2]

    for _, (department, _, dataset_path) in CONFIGS.items():
        validation = validate_dataset(repository_root.joinpath(dataset_path))
        assert validation["invalid_records"] == 0
        rows = [
            json.loads(line)
            for line in repository_root.joinpath(dataset_path)
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]

        assert len(rows) == 8
        assert {row["department"] for row in rows} == {department}
        assert sum(row["expected_behavior"] == "allow" for row in rows) == 6
        assert (
            sum(
                row["expected_behavior"] == "allow"
                and row["must_cite"] == "shared/company-handbook.md"
                for row in rows
            )
            == 1
        )
        denial_rows = [row for row in rows if row["expected_behavior"] == "deny"]
        assert len(denial_rows) == 2
        assert all(row["forbidden_terms"] for row in denial_rows)


def test_live_eval_configs_exclude_the_unusable_tool_call_evaluator() -> None:
    """ToolCallAccuracyEvaluator needs a tool_definitions input the CLI cannot supply.

    Every sample errors, and the gate blocks on evaluator errors, so including it
    would keep promotion permanently red for a reason unrelated to agent quality.
    """
    repository_root = Path(__file__).resolve().parents[2]

    for config_name in CONFIGS:
        config = yaml.safe_load(
            repository_root.joinpath("evals", config_name).read_text(encoding="utf-8")
        )
        assert "builtin.tool_call_accuracy" not in config["evaluators"]

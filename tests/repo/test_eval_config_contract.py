from pathlib import Path

import yaml

CONFIGS = {
    "eval.yaml": ("development-agent", "evals/data/development.jsonl"),
    "human-resources.yaml": (
        "human-resources-agent",
        "evals/data/human-resources.jsonl",
    ),
    "marketing.yaml": ("marketing-agent", "evals/data/marketing.jsonl"),
}
EVALUATORS = [
    "builtin.intent_resolution",
    "builtin.task_adherence",
    "builtin.relevance",
    "builtin.tool_call_accuracy",
    "builtin.groundedness",
]


def test_live_eval_configs_target_each_deployed_agent_and_dataset() -> None:
    repository_root = Path(__file__).resolve().parents[2]

    for config_name, (agent_name, dataset_path) in CONFIGS.items():
        config = yaml.safe_load(
            repository_root.joinpath("evals", config_name).read_text(encoding="utf-8")
        )

        assert config["agent"]["name"] == agent_name
        assert config["dataset"]["local_uri"] == dataset_path
        assert repository_root.joinpath(dataset_path).is_file()
        assert config["evaluators"] == EVALUATORS
        assert config["options"]["eval_model"] == "gpt-5.4-mini"
        assert config["options"]["pass_threshold"] == 0.70

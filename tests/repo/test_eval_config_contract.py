from pathlib import Path

import yaml


def test_configured_dataset_paths_resolve_from_repository_root() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load(
        repository_root.joinpath("evals", "eval.yaml").read_text(encoding="utf-8")
    )
    dataset_root = repository_root / config["dataset"]["local_uri"]

    assert dataset_root.is_dir()
    assert list(dataset_root.glob("*.jsonl"))

    configured_files = {
        repository_root / path
        for tier in ("smoke", "regression")
        for path in config[tier]["include_files"]
    }
    assert configured_files
    assert all(path.is_file() for path in configured_files)

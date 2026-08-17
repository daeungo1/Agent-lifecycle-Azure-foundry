from pathlib import Path

import yaml


def test_precommit_runs_uv_backed_ruff_checks_for_python_files() -> None:
    config = yaml.safe_load(Path(".pre-commit-config.yaml").read_text(encoding="utf-8"))
    assert [repository["repo"] for repository in config["repos"]] == ["local"]

    hooks = {hook["id"]: hook for repository in config["repos"] for hook in repository["hooks"]}
    assert set(hooks) == {"ruff-check", "ruff-format-check"}

    for hook in hooks.values():
        assert hook["language"] == "system"
        assert hook["types"] == ["python"]
        assert "--no-project" in hook["entry"]
        assert "--python 3.13" in hook["entry"]
        assert "--prerelease=allow" in hook["entry"]
        assert "--with-requirements requirements-dev.txt" in hook["entry"]

    assert hooks["ruff-check"]["entry"].endswith("python -m ruff check")
    assert hooks["ruff-format-check"]["entry"].endswith("python -m ruff format --check")

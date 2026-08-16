# Python Tooling and Pre-commit Design

## Purpose

Add a local pre-commit quality gate that runs Ruff lint and format checks through uv, and mirror the
format check in CI. Keep the current Foundry-compatible dependency files and do not change agent
logic, lifecycle scenarios, deployment behavior, or tests.

## Dependency Decision

The three requirements files remain:

- `requirements.txt`: Hosted Agent runtime dependencies.
- `requirements-ops.txt`: runtime plus deployment-hook dependencies.
- `requirements-dev.txt`: ops plus test, lint, formatting, and documentation dependencies.

`pyproject.toml` remains the package metadata and tool configuration file. It does not become the
sole dependency manifest.

This is required for the current Microsoft Foundry Python source deployment path:

- `dependencyResolution: remote_build` is documented to install Python dependencies from
  `requirements.txt`.
- `azd ai agent run` detects and installs Python projects from `requirements.txt`.
- Microsoft Foundry's official sample policy permits other dependency tools only in addition to a
  committed pip-compatible `requirements.txt`.

Deleting every requirements file is therefore out of scope until Microsoft documents pyproject-only
support for Hosted Agent remote builds.

References:

- <https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent-code>
- <https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/run-hosted-agent-locally>
- <https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/debug-hosted-agent>
- <https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/DEPENDENCY_POLICY.md>

## Pre-commit Configuration

Add `pre-commit` as a pinned development dependency in `requirements-dev.txt`.

Create `.pre-commit-config.yaml` with two local hooks:

1. `ruff-check`
   - Runs only for staged Python files.
   - Executes `python -m ruff check` through uv and `requirements-dev.txt`.
   - Does not auto-fix files.
2. `ruff-format-check`
   - Runs only for staged Python files.
   - Executes `python -m ruff format --check` through the same uv environment.
   - Does not format Markdown code fences or non-Python files.

Both hooks use `language: system`. This avoids declaring a second Ruff version in a third-party
pre-commit environment and keeps `requirements-dev.txt` as the Ruff version source.

The hooks use:

```text
uv run --no-project --python 3.13 --prerelease=allow
  --with-requirements requirements-dev.txt
```

`--prerelease=allow` remains necessary because the pinned Foundry hosting package depends on a
prerelease transitive package.

## Initial Formatting

The current branch has 27 tracked Python files that fail `ruff format --check`. Apply Ruff formatting
once to tracked `*.py` files only. Do not run the formatter over Markdown because current Ruff
versions also format Python code fences in Markdown, which would create unrelated documentation
churn.

The formatting commit must contain mechanical Python formatting only. No names, values, control
flow, imports, or assertions may be changed manually in that commit.

## CI

Keep the existing `python -m ruff check .` command. Add a Python-only format check using the tracked
file list:

```bash
git ls-files -z '*.py' | xargs -0 python -m ruff format --check
```

Do not run `ruff format --check .` because that includes Markdown code fences.

## Documentation

Update README local setup with:

```bash
pre-commit install
pre-commit run --all-files
```

Document that full pytest remains a CI and explicit developer command rather than a commit hook, so
commits remain fast.

## Testing and Acceptance

1. A repository contract test verifies both pre-commit hooks exist, use `language: system`, target
   Python files, and invoke uv with `requirements-dev.txt`.
2. A workflow contract test verifies CI runs both Ruff lint and Python-only format checks.
3. `pre-commit run --all-files` passes.
4. `ruff check .` passes.
5. Ruff format check passes for every tracked Python file.
6. All pytest tests pass with the same behavior assertions.
7. Bicep and deploy hook verification remain unchanged and passing.
8. The worktree is clean after the tooling commits.

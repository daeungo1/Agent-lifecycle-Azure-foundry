# Python Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add uv-backed Ruff lint and format checks to pre-commit and CI while preserving Foundry-compatible requirements files.

**Architecture:** Keep `requirements.txt`, `requirements-ops.txt`, and `requirements-dev.txt` because Foundry Python remote builds consume `requirements.txt`. Add local pre-commit hooks that reuse the pinned development environment, format tracked Python files once, and mirror the Python-only format check in CI.

**Tech Stack:** Python 3.13, uv 0.10.9+, pre-commit 4.3.0, Ruff 0.16.1, pytest.

## Global Constraints

- Preserve all agent logic, prompts, scenarios, evaluator settings, RBAC boundaries, and Build -> Evaluate -> Operate order.
- Keep `requirements.txt` committed for Foundry `remote_build` and local `azd ai agent run`.
- Use the existing global proxy through uv for dependency downloads.
- Run Ruff formatting only on tracked `*.py` files; do not format Markdown code fences.
- Pre-commit hooks must not modify files automatically.
- Full pytest remains outside pre-commit and continues to run in CI.
- Keep this work on `refactor/lifecycle-structure` for one pull request.

---

### Task 1: Add uv-backed pre-commit and CI contracts

**Files:**
- Create: `.pre-commit-config.yaml`
- Modify: `requirements-dev.txt`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `tests/repo/test_workflows.py`
- Modify: `tests/repo/test_documentation.py`
- Create: `tests/repo/test_precommit.py`

**Interfaces:**
- Consumes: `requirements-dev.txt` as the single Ruff/pre-commit version source
- Produces: `pre-commit` hooks `ruff-check` and `ruff-format-check`
- Produces: CI Python-only `ruff format --check`

- [ ] **Step 1: Write failing repository contract tests**

Create `tests/repo/test_precommit.py`:

```python
from pathlib import Path

import yaml


def test_precommit_runs_uv_backed_ruff_checks_for_python_files() -> None:
    config = yaml.safe_load(Path(".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = {
        hook["id"]: hook
        for repository in config["repos"]
        for hook in repository["hooks"]
    }

    assert set(hooks) == {"ruff-check", "ruff-format-check"}
    for hook in hooks.values():
        assert hook["language"] == "system"
        assert hook["types"] == ["python"]
        assert "--no-project" in hook["entry"]
        assert "--python 3.13" in hook["entry"]
        assert "--prerelease=allow" in hook["entry"]
        assert "--with-requirements requirements-dev.txt" in hook["entry"]

    assert hooks["ruff-check"]["entry"].endswith("python -m ruff check")
    assert hooks["ruff-format-check"]["entry"].endswith(
        "python -m ruff format --check"
    )
```

Extend `tests/repo/test_workflows.py::test_ci_workflow_contract`:

```python
assert "git ls-files -z '*.py'" in joined
assert "xargs -0 python -m ruff format --check" in joined
```

Extend the README command contract:

```python
assert "pre-commit install" in content
assert "pre-commit run --all-files" in content
```

- [ ] **Step 2: Run tests and verify missing configuration failures**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m pytest tests/repo/test_precommit.py \
    tests/repo/test_workflows.py::test_ci_workflow_contract \
    tests/repo/test_documentation.py::test_readme_architecture_and_commands_contract -v
```

Expected: failure because `.pre-commit-config.yaml`, CI format check, and README setup commands do
not exist.

- [ ] **Step 3: Add the pinned development dependency**

Append to `requirements-dev.txt`:

```text
pre-commit==4.3.0
```

- [ ] **Step 4: Add local pre-commit hooks**

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-check
        name: Ruff lint
        entry: >-
          uv run --no-project --python 3.13 --prerelease=allow
          --with-requirements requirements-dev.txt
          python -m ruff check
        language: system
        types: [python]
      - id: ruff-format-check
        name: Ruff format check
        entry: >-
          uv run --no-project --python 3.13 --prerelease=allow
          --with-requirements requirements-dev.txt
          python -m ruff format --check
        language: system
        types: [python]
```

- [ ] **Step 5: Mirror format validation in CI**

Add after Ruff lint:

```yaml
      - name: Ruff format
        run: git ls-files -z '*.py' | xargs -0 python -m ruff format --check
```

- [ ] **Step 6: Document local setup**

Add after development dependency installation:

```bash
pre-commit install
pre-commit run --all-files
```

State that pre-commit runs Ruff checks only; full pytest remains an explicit command and CI gate.

- [ ] **Step 7: Run focused tests**

Run the Step 2 command. Expected: tests pass.

- [ ] **Step 8: Commit**

```bash
git add .pre-commit-config.yaml requirements-dev.txt .github/workflows/ci.yml \
  README.md tests/repo/test_precommit.py tests/repo/test_workflows.py \
  tests/repo/test_documentation.py
git commit -m "build: add uv-backed pre-commit checks"
```

---

### Task 2: Format tracked Python and verify all quality gates

**Files:**
- Modify: tracked `*.py` files selected by `git ls-files`

**Interfaces:**
- Consumes: `.pre-commit-config.yaml`
- Produces: all tracked Python files compliant with Ruff 0.16.1 formatting

- [ ] **Step 1: Capture behavior baseline**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m pytest -q
```

Expected: 148 tests pass.

- [ ] **Step 2: Apply mechanical formatting to tracked Python files only**

Run:

```bash
git ls-files -z '*.py' | xargs -0 \
  uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m ruff format
```

Do not manually edit Python in this step.

- [ ] **Step 3: Verify formatting did not change behavior**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m pytest -q
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m ruff check .
git ls-files -z '*.py' | xargs -0 \
  uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m ruff format --check
```

Expected: 148 tests pass, Ruff lint passes, and every tracked Python file is formatted.

- [ ] **Step 4: Run pre-commit end to end**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  pre-commit run --all-files
```

Expected: `Ruff lint` and `Ruff format check` pass.

- [ ] **Step 5: Verify non-Python files were not formatted**

Run:

```bash
git diff --name-only | grep -vE '\.py$' || true
```

Expected: no non-Python changes beyond Task 1 configuration and documentation files.

- [ ] **Step 6: Commit mechanical formatting**

```bash
git add '*.py' tests src docs/tools
git commit -m "style: apply Ruff formatting"
```

- [ ] **Step 7: Run final repository verification**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m pytest -q
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  pre-commit run --all-files
az bicep build --file deploy/infra/main.bicep --stdout > /dev/null
az bicep build-params --file deploy/infra/main.bicepparam --stdout > /dev/null
git diff --check
git status --short
```

Expected: all tests and hooks pass, Bicep builds, and the worktree is clean.

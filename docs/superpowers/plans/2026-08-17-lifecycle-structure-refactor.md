# Lifecycle Structure Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the repository so Build, Evaluate, and Operate concerns are explicit, deployment is orchestrated by azd hooks, and department-derived names come from one source without changing agent logic or lifecycle scenarios.

**Architecture:** Keep `azure.yaml` and `departments.yaml` as root entry points, move Build assets under `deploy/`, keep evaluation assets under `evals/`, and split shipped runtime code (`lifecycle_agent`) from non-shipped operational code (`lifecycle_ops`). Use a single root `agent.py` entry point for all department services and thin cross-platform azd hook scripts that call tested Python modules.

**Tech Stack:** Python 3.13, uv 0.10.9+, Microsoft Agent Framework, Azure Developer CLI with Microsoft Foundry extension, Bicep, PyYAML, pytest, Ruff, POSIX shell, PowerShell.

## Global Constraints

- Preserve the Build -> Evaluate -> Operate lifecycle order.
- Do not change agent behavior, prompts, specialists, orchestration logic, evaluation thresholds, evaluator sets, dataset contents, RBAC boundary rules, or Azure resource topology.
- Preserve managed identity and `DefaultAzureCredential`; do not introduce credentials, tokens, or static secrets.
- Preserve department isolation: every agent may access only `shared` plus its matching department boundary.
- Use `uv` for all Python execution. Dependency downloads must use the existing global proxy configuration.
- Use `--prerelease=allow` because `agent-framework-foundry-hosting==1.0.0b260730` requires the prerelease `azure-ai-agentserver-responses>=1.0.0b8,<2`.
- Use `--no-project` during pre-refactor validation so uv does not create an unrequested `uv.lock`.
- Baseline evidence: `124 passed` and `All checks passed!` on 2026-08-17.
- Do not convert the four Bicep Search modules to a loop; named azd environment outputs must remain unchanged.
- Review every completed task for structural value, behavior drift, errors, and redundant tests before committing.
- Keep the 2026-08-16 design specification as the source for scope and risk decisions.

## Validation Commands

Before the dependency split:

```bash
UV_RUN="uv run --no-project --python 3.13 --prerelease=allow --with-requirements requirements.txt"
$UV_RUN python -m pytest -q
$UV_RUN python -m ruff check .
```

After the dependency split:

```bash
UV_RUN="uv run --no-project --python 3.13 --prerelease=allow --with-requirements requirements-dev.txt"
$UV_RUN python -m pytest -q
$UV_RUN python -m ruff check .
```

---

### Task 1: Normalize the Hosted Agent Entry Point

**Files:**
- Create: `agent.py`
- Move: `src/lifecycle_agent/main.py` -> `src/lifecycle_agent/host.py`
- Modify: `azure.yaml`
- Modify: `pyproject.toml`
- Modify: `tests/test_hosted_agent_packaging.py`
- Modify: `tests/test_main.py`
- Delete: `services/agents/development/main.py`
- Delete: `services/agents/human-resources/main.py`
- Delete: `services/agents/marketing/main.py`

**Interfaces:**
- Consumes: `lifecycle_agent.host.main() -> None`
- Produces: root script `agent.py`; all three `azure.yaml` services use `entryPoint: agent.py`

- [ ] **Step 1: Rewrite packaging tests to describe the shared entry point**

Replace the nested-entry-point assertion with:

```python
def test_hosted_agent_services_share_root_entrypoint() -> None:
    services = _load_azure_yaml()["services"]
    expected_departments = {
        "development-agent": "development",
        "human-resources-agent": "human-resources",
        "marketing-agent": "marketing",
    }

    for service_name, department in expected_departments.items():
        service = services[service_name]
        assert service["host"] == "azure.ai.agent"
        assert service["project"] == "."
        assert service["codeConfiguration"]["entryPoint"] == "agent.py"
        env_values = {
            item["name"]: item["value"]
            for item in service.get("environmentVariables", [])
            if isinstance(item, dict) and "name" in item and "value" in item
        }
        assert service["codeConfiguration"]["dependencyResolution"] == "remote_build"
        assert env_values["DEPARTMENT"] == department
        assert env_values["TOOLBOX_ENDPOINT"] == (
            "${TOOLBOX_ENDPOINT_" + department.replace("-", "_").upper() + "}"
        )
```

In the runtime-assets test, use the same name-based `env_values` lookup instead of
`service["environmentVariables"][1]`.

- [ ] **Step 2: Run the focused tests and verify they fail for the old layout**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m pytest tests/test_hosted_agent_packaging.py -v
```

Expected: failure because the three services still point to nested entry points.

- [ ] **Step 3: Add the single root bootstrap and move the host module**

Create `agent.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

if __name__ == "__main__":
    from lifecycle_agent.host import main

    main()
```

Move the existing host implementation without changing its logic:

```bash
git mv src/lifecycle_agent/main.py src/lifecycle_agent/host.py
```

Change each agent service in `azure.yaml`:

```yaml
codeConfiguration:
  runtime: python_3_13
  entryPoint: agent.py
  dependencyResolution: remote_build
```

Delete the now-redundant `services/` tree with targeted `git rm` commands.

- [ ] **Step 4: Configure the src layout for tests**

Change `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

Update imports in `tests/test_main.py` from `src.lifecycle_agent.main` to
`lifecycle_agent.host`.

In the same step, replace every `src.lifecycle_agent` import under `tests/` with
`lifecycle_agent`. Never allow both import roots: Python would load the same source as two module
objects, making monkeypatches and identity checks unreliable.

- [ ] **Step 5: Run focused and full verification**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m pytest tests/test_hosted_agent_packaging.py tests/test_main.py -v
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m pytest -q
```

Expected: focused tests pass; full suite reports at least 124 passing tests.

- [ ] **Step 6: Review the task before committing**

Check:

```bash
rg "services/agents|src\.lifecycle_agent|environmentVariables\]\[1\]" \
  agent.py azure.yaml src tests .github
git diff --check
```

Expected: no live-code references to the deleted entry points, no positional environment-variable
lookup, and no whitespace errors. Confirm that only the entry-point path changed; environment
values and host logic are byte-for-byte equivalent after the rename.

- [ ] **Step 7: Commit**

```bash
git add agent.py azure.yaml pyproject.toml src/lifecycle_agent/host.py \
  tests/test_hosted_agent_packaging.py tests/test_main.py services
git commit -m "refactor: share hosted agent entry point"
```

---

### Task 2: Establish Department and Naming Sources of Truth

**Files:**
- Create: `src/lifecycle_agent/settings.py`
- Create: `src/lifecycle_agent/departments.py`
- Create: `src/lifecycle_ops/__init__.py`
- Create: `src/lifecycle_ops/naming.py`
- Create: `tests/test_naming.py`
- Modify: `src/lifecycle_agent/host.py`
- Modify: `src/lifecycle_agent/orchestration.py`
- Modify: `src/lifecycle_agent/__init__.py`
- Modify: `tests/test_config.py`
- Delete: `src/lifecycle_agent/config.py`

**Interfaces:**
- Produces: `Settings.from_env() -> Settings`
- Produces: `load_departments(path: Path | str = Path("departments.yaml")) -> dict[str, DepartmentConfig]`
- Produces: `select_department(configs, name) -> DepartmentConfig`
- Produces: naming functions `agent_name`, `env_suffix`, `toolbox_name`, `toolbox_file`,
  `knowledge_path`, `continuous_eval_name`, and `continuous_rule_id`

- [ ] **Step 1: Add failing tests for repository discovery and derived names**

Create `tests/test_naming.py`:

```python
from lifecycle_agent.departments import load_departments
from lifecycle_ops.naming import (
    agent_name,
    continuous_eval_name,
    continuous_rule_id,
    env_suffix,
    knowledge_path,
    toolbox_file,
    toolbox_name,
)


def test_names_are_derived_from_department_configuration() -> None:
    departments = load_departments()
    assert tuple(departments) == ("development", "human-resources", "marketing")

    assert agent_name("human-resources") == "human-resources-agent"
    assert env_suffix("human-resources") == "HUMAN_RESOURCES"
    assert knowledge_path("human-resources").as_posix() == "knowledge/human-resources"
    assert toolbox_name("human-resources") == "human-resources-knowledge-toolbox"
    assert toolbox_file("human-resources").as_posix() == "toolboxes/human-resources.yaml"
    assert continuous_eval_name("human-resources") == "continuous-eval-human-resources"
    assert continuous_rule_id("human-resources") == (
        "continuous-response-completed-human-resources"
    )
```

Add a config test that changes the current working directory and still loads the root file:

```python
def test_load_departments_finds_repository_file_outside_repo_cwd(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    assert set(load_departments()) == {
        "development",
        "human-resources",
        "marketing",
    }
```

- [ ] **Step 2: Run the tests and verify imports fail**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m pytest tests/test_config.py tests/test_naming.py -v
```

Expected: import failure for `lifecycle_agent.departments` or `lifecycle_ops.naming`.

- [ ] **Step 3: Split settings from department topology**

Move `REQUIRED_ENV_VARS` and `RESPONSES_PROTOCOL_VERSION` unchanged into `settings.py`. Move
`SpecialistConfig`, `DepartmentConfig`, `load_departments`, and `select_department` into
`departments.py`. `Settings.from_env()` keeps its existing missing-variable and unknown-department
errors but validates against `load_departments()` instead of `ALLOWED_DEPARTMENTS`:

```python
department = os.environ["DEPARTMENT"]
if department not in load_departments():
    raise ValueError(f"Unknown department: {department}")
```

Use this root discovery:

```python
def _find_repository_file(filename: str) -> Path:
    for parent in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        candidate = parent / filename
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Could not find repository file: {filename}")


def load_departments(
    path: Path | str = Path("departments.yaml"),
) -> dict[str, DepartmentConfig]:
    candidate = Path(path)
    full_path = candidate if candidate.is_absolute() else _find_repository_file(str(candidate))
    # Keep the existing parsing and validation logic unchanged below this line.
```

Remove the expected-list comparison against `ALLOWED_DEPARTMENTS`. Replace it with structural
validation that rejects an empty list and duplicate names:

```python
if not departments:
    raise ValueError("departments.yaml must define at least one department")

if name in result:
    raise ValueError(f"Duplicate department: {name}")
```

Do not add aliases, default departments, silent fallback data, or other schema changes. The checked
in YAML remains the same three-department scenario. `tests/test_naming.py` deliberately asserts the
exact ordered tuple `("development", "human-resources", "marketing")`; a roster edit therefore
requires an explicit test and review change rather than silently changing the scenario.

- [ ] **Step 4: Implement naming as pure derivation**

Create `src/lifecycle_ops/naming.py`:

```python
from __future__ import annotations

from pathlib import Path

from lifecycle_agent.departments import load_departments


def department_names() -> tuple[str, ...]:
    return tuple(load_departments())


def require_department(department: str) -> str:
    if department not in load_departments():
        raise ValueError(f"Unknown department: {department}")
    return department


def agent_name(department: str) -> str:
    return f"{require_department(department)}-agent"


def env_suffix(department: str) -> str:
    return require_department(department).replace("-", "_").upper()


def knowledge_path(department: str) -> Path:
    return Path("knowledge") / require_department(department)


def toolbox_name(department: str) -> str:
    return f"{require_department(department)}-knowledge-toolbox"


def toolbox_file(
    department: str,
    root: Path = Path("toolboxes"),
) -> Path:
    return root / f"{require_department(department)}.yaml"


def continuous_eval_name(department: str) -> str:
    return f"continuous-eval-{require_department(department)}"


def continuous_rule_id(department: str) -> str:
    return f"continuous-response-completed-{require_department(department)}"
```

`shared` remains a knowledge boundary, not a department. Do not make it pass
`require_department`.

- [ ] **Step 5: Update imports and delete the old mixed module**

Update runtime imports:

```python
from .departments import load_departments, select_department
from .settings import Settings
```

Update `orchestration.py`:

```python
from .departments import DepartmentConfig
from .settings import Settings
```

Export the same public configuration symbols from `lifecycle_agent/__init__.py` so external callers
do not lose supported imports.

- [ ] **Step 6: Run focused and full tests**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m pytest tests/test_config.py tests/test_naming.py \
    tests/test_main.py tests/test_orchestration.py -v
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m pytest -q
```

Expected: all focused tests pass and total passing test count is at least 125.

- [ ] **Step 7: Review for value and behavior drift**

Run:

```bash
rg "ALLOWED_DEPARTMENTS|DEPARTMENT_BY_AGENT|DEPARTMENT_AGENT_NAMES|KNOWN_BOUNDARIES" \
  src tests
git diff --check
```

Expected: `ALLOWED_DEPARTMENTS` is gone from runtime configuration. Remaining hardcoded maps in
old scripts are expected until Task 3. Verify no prompt path, specialist count, exception message,
or environment requirement changed.

- [ ] **Step 8: Commit**

```bash
git add src/lifecycle_agent src/lifecycle_ops tests/test_config.py tests/test_naming.py
git commit -m "refactor: centralize department naming"
```

---

### Task 3: Move Operational Modules into a Non-Shipped Package

**Files:**
- Create: `src/lifecycle_ops/azd_env.py`
- Create: `src/lifecycle_ops/provisioning/__init__.py`
- Create: `src/lifecycle_ops/evaluation/__init__.py`
- Create: `src/lifecycle_ops/operations/__init__.py`
- Create: `src/lifecycle_ops/operations/agent365/__init__.py`
- Move: `scripts/provision_knowledge_bases.py` -> `src/lifecycle_ops/provisioning/knowledge_bases.py`
- Move: `scripts/set_agent_rbac.py` -> `src/lifecycle_ops/provisioning/rbac.py`
- Move: `scripts/configure_continuous_evaluation.py` -> `src/lifecycle_ops/provisioning/continuous_eval.py`
- Move: `evals/validate_dataset.py` -> `src/lifecycle_ops/evaluation/dataset.py`
- Move: `scripts/validate_eval_results.py` -> `src/lifecycle_ops/evaluation/gate.py`
- Move: `scripts/verify_deployment.py` -> `src/lifecycle_ops/operations/deployment_check.py`
- Move: `scripts/agent365/configure_observability.py` -> `src/lifecycle_ops/operations/agent365/readiness.py`
- Move: `scripts/agent365/verify_registry.py` -> `src/lifecycle_ops/operations/agent365/registry.py`
- Modify: corresponding tests and imports

**Interfaces:**
- Produces: `get_values() -> dict[str, str]`
- Produces: `set_value(name: str, value: str) -> None`
- Preserves every existing module-level function signature and CLI exit-code contract

- [ ] **Step 1: Write failing shared azd environment tests**

Add to a new `tests/test_azd_env.py`:

```python
from lifecycle_ops.azd_env import get_values, set_value


def test_get_values_parses_azd_output(monkeypatch) -> None:
    monkeypatch.setattr(
        "lifecycle_ops.azd_env.run_command",
        lambda command: 'FOO="alpha"\nBAR="beta value"\n',
    )
    assert get_values() == {"FOO": "alpha", "BAR": "beta value"}


def test_set_value_uses_noninteractive_azd_command(monkeypatch) -> None:
    commands = []
    monkeypatch.setattr(
        "lifecycle_ops.azd_env.run_command",
        lambda command: commands.append(command) or "",
    )
    set_value("TOOLBOX_ENDPOINT_DEVELOPMENT", "https://example.test")
    assert commands == [[
        "azd", "env", "set", "TOOLBOX_ENDPOINT_DEVELOPMENT",
        "https://example.test", "--no-prompt",
    ]]
```

- [ ] **Step 2: Verify the new tests fail**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m pytest tests/test_azd_env.py -v
```

Expected: import failure for `lifecycle_ops.azd_env`.

- [ ] **Step 3: Implement the shared azd environment adapter**

Create `azd_env.py` with one subprocess boundary and the existing quote parsing behavior:

```python
from __future__ import annotations

import shlex
import subprocess


def run_command(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def get_values() -> dict[str, str]:
    output = run_command(["azd", "env", "get-values", "--no-prompt"])
    values: dict[str, str] = {}
    for line in output.splitlines():
        if not line or "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        parsed = shlex.split(raw_value)
        values[name] = parsed[0] if parsed else ""
    return values


def set_value(name: str, value: str) -> None:
    run_command(["azd", "env", "set", name, value, "--no-prompt"])
```

If existing tests demonstrate different quote semantics, preserve the tested semantics instead of
forcing this sample implementation.

- [ ] **Step 4: Move modules without changing their internal logic**

Use `git mv` for the eight modules and delete `evals/__init__.py` after moving its only Python
module. Update only import paths and command entry points. Retain all HTTP calls, SDK calls,
exception behavior, return structures, report JSON, and CLI arguments.

Replace private department maps with Task 2 functions. Examples:

```python
for department in department_names():
    current_agent_name = agent_name(department)
    current_suffix = env_suffix(department)
```

Keep the `shared` boundary explicit:

```python
boundaries = ("shared", *department_names())
```

- [ ] **Step 5: Update tests to import moved modules**

Examples:

```python
from lifecycle_ops.evaluation.dataset import validate_dataset
from lifecycle_ops.evaluation.gate import validate_results
from lifecycle_ops.operations.deployment_check import verify_agents
from lifecycle_ops.provisioning.continuous_eval import configure_continuous_evaluation
from lifecycle_ops.provisioning.rbac import (
    build_role_assignment_create_args,
    build_role_assignment_list_args,
)
```

Use the preserved names shown above: `validate_dataset`, `validate_results`, `verify_agents`,
`configure_continuous_evaluation`, `build_role_assignment_create_args`, and
`build_role_assignment_list_args`. Do not rename public functions in this task.

- [ ] **Step 6: Run all operational tests**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m pytest \
    tests/test_azd_env.py \
    tests/test_agent365_status.py \
    tests/test_agent_rbac_matrix.py \
    tests/test_continuous_eval.py \
    tests/test_eval_datasets.py \
    tests/test_validate_eval_results.py \
    tests/test_workflows.py -v
```

Expected: all selected tests pass with unchanged assertion values.

- [ ] **Step 7: Review for hidden logic changes and redundant adapters**

Run:

```bash
git diff --stat
git diff -- src/lifecycle_ops
rg "subprocess\.run.*azd|azd.*env.*get-values|azd.*env.*set" src/lifecycle_ops
```

Expected: azd environment access is centralized except command builders intentionally tested as
pure data. Reject any incidental change to request payloads, role names, evaluator lists, report
schemas, CLI options, or status values.

- [ ] **Step 8: Run full verification and commit**

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m pytest -q
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m ruff check .
git add src/lifecycle_ops scripts evals tests
git commit -m "refactor: separate lifecycle operations"
```

Expected: at least the baseline 124 tests plus new tests pass; Ruff passes.

---

### Task 4: Consolidate Toolbox Provisioning in Python

**Files:**
- Move and merge: `scripts/toolbox_ops.py` -> `src/lifecycle_ops/provisioning/toolboxes.py`
- Modify: `tests/test_toolbox_ops.py`
- Create: `tests/test_toolbox_command_parity.py`
- Delete: `scripts/configure_toolboxes.ps1`

**Interfaces:**
- Preserves: existing pure command-builder functions from `toolbox_ops.py`
- Produces: `configure_toolboxes() -> list[dict[str, str]]`
- Produces CLI: `python -m lifecycle_ops.provisioning.toolboxes`

- [ ] **Step 1: Capture PowerShell command parity before deletion**

Create a test that extracts the four final operations from the PowerShell script and compares their
semantic inputs with Python specs:

```python
def test_python_specs_match_powershell_department_operations() -> None:
    powershell = Path("scripts/configure_toolboxes.ps1").read_text(encoding="utf-8")
    for department in department_names():
        suffix = env_suffix(department)
        assert f'KB_MCP_ENDPOINT_{suffix}' in powershell
        assert toolbox_name(department) in powershell
        assert f"toolboxes/{department}.yaml" in powershell
        assert f"TOOLBOX_ENDPOINT_{suffix}" in powershell
```

This temporary test protects the migration. It is replaced in this task by direct Python
command-sequence assertions before the PowerShell source is deleted.

- [ ] **Step 2: Run parity and existing toolbox tests**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m pytest tests/test_toolbox_ops.py tests/test_toolbox_command_parity.py -v
```

Expected: both pass against the pre-migration implementation.

- [ ] **Step 3: Add failing CLI orchestration test**

Add:

```python
def test_configure_toolboxes_processes_each_department(monkeypatch) -> None:
    configured = []
    monkeypatch.setattr(
        toolboxes,
        "configure_department_toolbox",
        lambda department: configured.append(department) or {
            "department": department,
        },
    )

    assert toolboxes.configure_toolboxes() == [
        {"department": "development"},
        {"department": "human-resources"},
        {"department": "marketing"},
    ]
    assert configured == ["development", "human-resources", "marketing"]
```

Expected before implementation: failure because `configure_toolboxes` is undefined.

- [ ] **Step 4: Merge execution into the tested Python module**

Move the pure Python module, then add orchestration that uses its existing command builders,
`lifecycle_ops.azd_env`, and `subprocess.run(check=True, capture_output=True, text=True)`.

The control flow must remain:

```python
def configure_toolboxes() -> list[dict[str, str]]:
    configured = []
    for department in department_names():
        configured.append(configure_department_toolbox(department))
    return configured


def main() -> int:
    configure_toolboxes()
    return 0
```

Do not change connection names, audience, authentication mode, publication version, endpoint
environment variable names, or exit-code behavior. No new machine-readable stdout contract is
introduced; azd command output remains operational logging as it was in PowerShell.

- [ ] **Step 5: Move toolbox paths to the future target path**

Update `toolbox_file` expectations to `deploy/toolboxes/<department>.yaml` only after Task 5 moves
those files. Until then, make the root directory an injected parameter with the current default:

```python
def toolbox_file(department: str, root: Path = Path("toolboxes")) -> Path:
    return root / f"{require_department(department)}.yaml"
```

Task 5 changes the default to `Path("deploy/toolboxes")`. This prevents an intermediate broken
commit.

- [ ] **Step 6: Delete the PowerShell implementation after behavioral tests pass**

Run focused tests first:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m pytest tests/test_toolbox_ops.py tests/test_toolbox_command_parity.py -v
```

Then replace `tests/test_toolbox_command_parity.py` with direct command-sequence assertions against
`configure_department_toolbox` and delete `scripts/configure_toolboxes.ps1`. No test may read the
deleted source from Git history.

- [ ] **Step 7: Review command equivalence**

Compare the old file from Git with the new implementation:

```bash
git show HEAD:scripts/configure_toolboxes.ps1 > /tmp/configure_toolboxes.ps1.before
rg "connection|toolbox|publish|TOOLBOX_ENDPOINT|KB_MCP_ENDPOINT" \
  /tmp/configure_toolboxes.ps1.before src/lifecycle_ops/provisioning/toolboxes.py
rm /tmp/configure_toolboxes.ps1.before
```

Expected: every old operation has a Python equivalent. No new Azure operation appears.

- [ ] **Step 8: Run full tests and commit**

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m pytest -q
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m ruff check .
git add src/lifecycle_ops/provisioning/toolboxes.py scripts tests
git commit -m "refactor: consolidate toolbox provisioning"
```

---

### Task 5: Group Deploy Assets and Add azd Hooks

**Files:**
- Create: `deploy/hooks/postprovision.sh`
- Create: `deploy/hooks/postprovision.ps1`
- Create: `deploy/hooks/postdeploy.sh`
- Create: `deploy/hooks/postdeploy.ps1`
- Move: `infra/` -> `deploy/infra/`
- Move: `toolboxes/` -> `deploy/toolboxes/`
- Create: `tests/test_hooks_contract.py`
- Modify: `azure.yaml`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/deploy-evaluate.yml`
- Modify: infra, toolbox, workflow, and packaging tests containing old paths

**Interfaces:**
- `postprovision`: knowledge bases -> toolboxes
- `postdeploy`: RBAC -> continuous evaluation
- Preserves named Bicep outputs and the explicit `azd provision` then `azd deploy` workflow

- [ ] **Step 1: Write hook contract tests before creating hooks**

Create:

```python
POSTPROVISION_MODULES = [
    "lifecycle_ops.provisioning.knowledge_bases",
    "lifecycle_ops.provisioning.toolboxes",
]
POSTDEPLOY_MODULES = [
    "lifecycle_ops.provisioning.rbac",
    "lifecycle_ops.provisioning.continuous_eval",
]


def _invoked_modules(path: Path) -> list[str]:
    return re.findall(r"python -m ([a-zA-Z0-9_.]+)", path.read_text(encoding="utf-8"))


def test_hook_platform_variants_have_identical_order() -> None:
    assert _invoked_modules(Path("deploy/hooks/postprovision.sh")) == POSTPROVISION_MODULES
    assert _invoked_modules(Path("deploy/hooks/postprovision.ps1")) == POSTPROVISION_MODULES
    assert _invoked_modules(Path("deploy/hooks/postdeploy.sh")) == POSTDEPLOY_MODULES
    assert _invoked_modules(Path("deploy/hooks/postdeploy.ps1")) == POSTDEPLOY_MODULES


def test_postprovision_does_not_require_deployed_agents() -> None:
    modules = _invoked_modules(Path("deploy/hooks/postprovision.sh"))
    assert "lifecycle_ops.provisioning.rbac" not in modules
    assert "lifecycle_ops.provisioning.continuous_eval" not in modules
```

Also load `azure.yaml` and assert every declared hook file exists.

- [ ] **Step 2: Run the hook tests and verify missing-file failures**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m pytest tests/test_hooks_contract.py -v
```

Expected: failure because `deploy/hooks/` does not exist.

- [ ] **Step 3: Move deployment assets without editing Bicep content**

Run:

```bash
mkdir -p deploy
git mv infra deploy/infra
git mv toolboxes deploy/toolboxes
```

Update `azure.yaml`:

```yaml
infra:
  provider: microsoft.foundry
  path: deploy/infra
```

Update the toolbox path default:

```python
def toolbox_file(
    department: str,
    root: Path = Path("deploy/toolboxes"),
) -> Path:
```

- [ ] **Step 4: Add thin platform hook scripts**

`postprovision.sh`:

```sh
#!/bin/sh
set -eu
export PYTHONPATH="${PWD}/src${PYTHONPATH:+:${PYTHONPATH}}"
python -m lifecycle_ops.provisioning.knowledge_bases
python -m lifecycle_ops.provisioning.toolboxes
```

`postprovision.ps1`:

```powershell
$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = Join-Path $PWD 'src'
python -m lifecycle_ops.provisioning.knowledge_bases
python -m lifecycle_ops.provisioning.toolboxes
```

`postdeploy.sh`:

```sh
#!/bin/sh
set -eu
export PYTHONPATH="${PWD}/src${PYTHONPATH:+:${PYTHONPATH}}"
python -m lifecycle_ops.provisioning.rbac
python -m lifecycle_ops.provisioning.continuous_eval
```

`postdeploy.ps1`:

```powershell
$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = Join-Path $PWD 'src'
python -m lifecycle_ops.provisioning.rbac
python -m lifecycle_ops.provisioning.continuous_eval
```

Mark only `.sh` files executable.

- [ ] **Step 5: Declare hooks in azure.yaml**

Use the azd hook schema verified against the installed CLI:

```yaml
hooks:
  postprovision:
    posix:
      shell: sh
      run: ./deploy/hooks/postprovision.sh
    windows:
      shell: pwsh
      run: ./deploy/hooks/postprovision.ps1
  postdeploy:
    posix:
      shell: sh
      run: ./deploy/hooks/postdeploy.sh
    windows:
      shell: pwsh
      run: ./deploy/hooks/postdeploy.ps1
```

This shape is the documented azd OS-specific hook schema. Confirm the checked-in YAML parses and
the contract test sees the four paths; live hook execution remains part of deferred Azure
verification.

- [ ] **Step 6: Simplify the deployment workflow without changing phase order**

Remove manual workflow calls to knowledge bases, toolboxes, RBAC, and continuous evaluation.
Retain these explicit stages:

```text
Build
azd provision  (postprovision hook runs KB -> toolboxes)
azd deploy     (postdeploy hook runs RBAC -> continuous evaluation)
three-agent smoke
Evaluate
Operate verification
artifact upload
```

Do not replace the two azd commands with `azd up`; separate commands keep failure attribution clear.

- [ ] **Step 7: Update all moved path contracts**

Use:

```bash
rg "\binfra/|\btoolboxes/" azure.yaml .github tests src docs README.md
```

Update live paths to `deploy/infra/` and `deploy/toolboxes/`. Do not rewrite historical path text in
committed plan documents except the original 2026-08-02 design document in Task 8.

- [ ] **Step 8: Validate hooks, workflows, and Bicep**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements.txt \
  python -m pytest tests/test_hooks_contract.py tests/test_workflows.py \
    tests/test_infra_static.py tests/test_toolbox_boundaries.py \
    tests/test_hosted_agent_packaging.py -v
az bicep build --file deploy/infra/main.bicep
```

Expected: tests pass and Bicep emits no errors. Compare Bicep output names with the baseline:

```bash
rg "^output " deploy/infra/main.bicep
```

Expected: named outputs are unchanged.

- [ ] **Step 9: Review lifecycle ordering and commit**

Read the workflow and hooks together. Confirm Build -> provision -> postprovision -> deploy ->
postdeploy -> smoke -> Evaluate -> Operate. Confirm no state-changing step moved into Evaluate or
Operate verification.

```bash
git diff --check
git add azure.yaml deploy .github src/lifecycle_ops tests infra toolboxes
git commit -m "refactor: orchestrate deployment with azd hooks"
```

---

### Task 6: Move Evaluation Configuration and Split Dependencies

**Files:**
- Move: `eval.yaml` -> `evals/eval.yaml`
- Move: `scripts/render-excalidraw.py` -> `docs/tools/render_excalidraw.py`
- Create: `requirements-ops.txt`
- Create: `requirements-dev.txt`
- Modify: `requirements.txt`
- Modify: `.agentignore`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/deploy-evaluate.yml`
- Modify: evaluation and documentation tests

**Interfaces:**
- Preserves all evaluation thresholds, evaluator names, include files, and JSONL contents
- Proves configured dataset paths resolve from the repository root without changing gate behavior

- [ ] **Step 1: Add a failing evaluation path contract test**

Create `tests/test_eval_config_contract.py`:

```python
from pathlib import Path

import yaml


def test_configured_dataset_paths_resolve_from_repository_root() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load(Path("evals/eval.yaml").read_text(encoding="utf-8"))
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
```

- [ ] **Step 2: Run the test and confirm the future path is absent**

Run the focused test. Expected: failure because `evals/eval.yaml` does not exist yet. This test
protects path resolution without modifying validation logic or accepted result formats.

- [ ] **Step 3: Move evaluation and documentation assets**

Run:

```bash
git mv eval.yaml evals/eval.yaml
mkdir -p docs/tools
git mv scripts/render-excalidraw.py docs/tools/render_excalidraw.py
```

Keep `dataset.local_uri: evals/data` unchanged because commands run from repository root. Update all
CLI invocations to `--config evals/eval.yaml`.

- [ ] **Step 4: Split runtime, operations, and development dependencies**

Keep runtime requirements only in `requirements.txt`:

```text
agent-framework-foundry-hosting==1.0.0b260730
agent-framework-foundry==1.10.4
azure-ai-projects==2.3.0
azure-identity==1.26.0b2
python-dotenv==1.2.2
PyYAML==6.0.3
microsoft-opentelemetry==1.3.6
azure-monitor-opentelemetry==1.8.9
```

Create `requirements-ops.txt`:

```text
-r requirements.txt
httpx==0.28.1
```

Create `requirements-dev.txt`:

```text
-r requirements-ops.txt
pytest==9.1.1
ruff==0.16.1
debugpy==1.8.21
Pillow==12.3.0
```

Before finalizing, verify whether the hosted runtime uses `httpx`:

```bash
rg "^(import|from) httpx" src/lifecycle_agent
```

Expected: no matches, so `httpx` remains operations-only.

- [ ] **Step 5: Exclude non-runtime assets from hosted packaging**

Update `.agentignore` to exclude:

```text
deploy/
docs/
evals/
knowledge/
src/lifecycle_ops/
tests/
```

Keep `departments.yaml`, `requirements.txt`, `agent.py`, and `src/lifecycle_agent/` included.

- [ ] **Step 6: Update CI and deploy dependency installation**

CI and the deployment workflow install `requirements-dev.txt` because both run Ruff and pytest.
Local operators who deploy without the test toolchain install `requirements-ops.txt`:

```bash
uv pip install --system --prerelease=allow -r requirements-ops.txt
```

Preserve the workflows' current pip-based installation and change only the requirements file path;
local verification continues to use uv. Do not mix dependency tooling in one workflow.

- [ ] **Step 7: Verify dependency and evaluation boundaries**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m pytest tests/test_eval_config_contract.py tests/test_eval_datasets.py \
    tests/test_validate_eval_results.py tests/test_documentation.py \
    tests/test_hosted_agent_packaging.py -v
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m ruff check .
```

Confirm `evals/data/*.jsonl` checksums are unchanged:

```bash
git diff --exit-code -- evals/data
```

- [ ] **Step 8: Review necessity and commit**

Confirm every dependency is consumed:

```bash
rg "import (httpx|pytest|ruff|debugpy|PIL)|from (httpx|PIL)" . \
  --glob "*.py"
```

Remove no dependency solely because the search is empty if it is a documented CLI tool; verify CI
usage first. Commit:

```bash
git add evals docs/tools requirements.txt requirements-ops.txt requirements-dev.txt .agentignore \
  .github src/lifecycle_ops/evaluation tests scripts
git commit -m "refactor: separate evaluation and development assets"
```

---

### Task 7: Reorganize and Prune Tests by Responsibility

**Files:**
- Move: runtime tests -> `tests/agent/`
- Move: operational tests -> `tests/ops/`
- Move: repository contract tests -> `tests/repo/`
- Delete only tests proven redundant by identical assertions
- Modify: test helper repository-root calculations

**Interfaces:**
- Preserves behavioral coverage and the baseline assertion intent
- Produces test groups aligned with `lifecycle_agent`, `lifecycle_ops`, and repository contracts

- [ ] **Step 1: Inventory tests before moving**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m pytest --collect-only -q > /tmp/tests-before.txt
wc -l /tmp/tests-before.txt
```

Record collected test node IDs. This is the comparison source for pruning.

- [ ] **Step 2: Classify files**

Use these ownership rules:

```text
tests/agent/  imports lifecycle_agent or tests hosted runtime packaging
tests/ops/    imports lifecycle_ops or tests its CLI/report behavior
tests/repo/   tests Bicep, YAML workflows, hooks, documentation, static repository contracts
```

Move with `git mv`; do not rename test functions in the same step.

- [ ] **Step 3: Fix repository-root helpers**

Nested tests must not rely on `parents[1]`. Add one helper:

```python
def repository_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("Could not find repository root")
```

Place it in `tests/conftest.py` as a fixture only if at least three files use it. Otherwise keep
focused local helpers to avoid a premature test utility abstraction.

- [ ] **Step 4: Identify redundant tests by assertion, not name**

Compare collected node IDs and test bodies:

```bash
rg "^def test_" tests -n
```

A test may be deleted only when another test executes the same public entry point with the same
inputs and asserts the same outputs or error. Do not delete:

- department boundary tests,
- workflow ordering tests,
- packaging inclusion/exclusion tests,
- evaluation dataset path contracts,
- cross-platform hook parity,
- status-contract tests,
- tests that distinguish malformed input from missing input.

The direct Python command-sequence tests from Task 4 stay because they cover the execution contract
formerly exercised by PowerShell. Only a migration-only test that still refers to the deleted
PowerShell file may be removed.

- [ ] **Step 5: Run collection and compare**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m pytest --collect-only -q > /tmp/tests-after.txt
diff -u /tmp/tests-before.txt /tmp/tests-after.txt || true
```

Expected: path changes plus explicitly justified duplicate removal only. The passing test count may
drop below 124 only by the number of documented duplicate tests removed; behavioral assertion
coverage must not decrease.

- [ ] **Step 6: Run full verification and review test quality**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m pytest -v
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m ruff check .
```

Review failures as evidence of a bad move or hidden coupling; do not weaken assertions to make the
suite pass.

- [ ] **Step 7: Commit**

```bash
rm /tmp/tests-before.txt /tmp/tests-after.txt
git add tests
git commit -m "test: organize lifecycle coverage by responsibility"
```

---

### Task 8: Align Documentation and Run Final Structural Review

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/operations.md`
- Modify: `docs/superpowers/specs/2026-08-02-agent-lifecycle-design.md`
- Modify: documentation contract tests where necessary
- Delete: `scripts/verify_environment.ps1`
- Delete: remaining empty `scripts/` and `services/` directories

**Interfaces:**
- Documents the implemented Build -> Evaluate -> Operate flow
- Does not claim live Azure verification unless it was actually run

- [ ] **Step 1: Add or update documentation contract tests**

Assert:

```python
def test_readme_uses_azd_hook_deployment_flow() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "azd provision --no-prompt" in readme
    assert "azd deploy --no-prompt" in readme
    assert "scripts/provision_knowledge_bases.py" not in readme
    assert "scripts/configure_toolboxes.ps1" not in readme


def test_original_design_records_real_dependency_order() -> None:
    design = Path(
        "docs/superpowers/specs/2026-08-02-agent-lifecycle-design.md"
    ).read_text(encoding="utf-8")
    sequence = [
        "azd provision",
        "knowledge bases",
        "toolboxes",
        "azd deploy",
        "RBAC",
        "continuous evaluation",
    ]
    positions = [design.index(term) for term in sequence]
    assert positions == sorted(positions)
```

Adapt capitalization to the final prose, but keep the ordering assertion.

- [ ] **Step 2: Update README**

Document:

```bash
azd extension install microsoft.foundry --no-prompt
azd provision --no-prompt
azd deploy --no-prompt
```

Explain that `postprovision` creates knowledge bases then toolboxes, while `postdeploy` applies RBAC
then registers continuous evaluation. Keep evaluation gate and Operate verification commands
separate and in the same order as the workflow.

- [ ] **Step 3: Correct the 2026-08-02 design document**

Update its repository tree and deployment order. Remove unimplemented `.foundry/` and `.vscode/`
entries. Remove the claim that the workflow verifies continuous-evaluation enabled state unless an
actual verification implementation exists.

Do not rewrite its historical purpose, scenario, or acceptance intent.

- [ ] **Step 4: Clarify evaluation behavior in operations documentation**

Record:

```text
Deployment gate: fixed datasets, five evaluators, blocking.
Continuous evaluation: sampled production responses, three lower-cost evaluators, non-blocking,
bounded to 20 hourly runs.
The registration command is idempotent configuration; Foundry executes subsequent evaluations.
```

Do not change evaluator lists or limits.

- [ ] **Step 5: Update repository instructions**

Add to `AGENTS.md`:

```text
- Keep deploy hooks thin; lifecycle logic belongs in lifecycle_ops.
- Keep indexed content under knowledge/ and configuration outside it.
- Use departments.yaml and lifecycle_ops.naming for department-derived values.
- Verify Build -> Evaluate -> Operate ordering after workflow changes.
```

- [ ] **Step 6: Remove the unused environment verifier**

Before deletion, prove it has no live caller:

```bash
rg "verify_environment" . \
  --glob '!docs/superpowers/plans/*.md' \
  --glob '!docs/superpowers/specs/*.md'
```

Expected: no matches outside the file itself. Delete `scripts/verify_environment.ps1`; do not
replace it because current CI, deployment, and local instructions never invoke it.

- [ ] **Step 7: Run structural searches**

Run:

```bash
test ! -d scripts
test ! -d services
rg "scripts/|services/agents|infra/main\.bicep|toolboxes/" \
  README.md AGENTS.md azure.yaml .github src tests \
  docs/operations.md docs/identity-and-access.md
rg "development.*human-resources.*marketing|ALLOWED_DEPARTMENTS|DEPARTMENT_BY_AGENT" \
  src --glob "*.py"
```

Expected: no stale live paths; no private Python roster. Declarative service and toolbox files may
still enumerate departments.

- [ ] **Step 8: Run final local verification**

Run:

```bash
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m pytest -v
uv run --no-project --python 3.13 --prerelease=allow \
  --with-requirements requirements-dev.txt \
  python -m ruff check .
az bicep build --file deploy/infra/main.bicep
git diff --check
git status --short
```

Expected: all retained and new tests pass, Ruff passes, Bicep builds, and only intended changes are
present.

- [ ] **Step 9: Inspect the final package boundary**

Using `.agentignore`, enumerate the files that would be shipped and verify:

```text
Included: agent.py, azure.yaml-required runtime metadata, departments.yaml, requirements.txt,
src/lifecycle_agent/**.
Excluded: deploy/**, docs/**, evals/**, knowledge/**, src/lifecycle_ops/**, tests/**.
```

Verify that excluding `knowledge/` is safe because deployed agents retrieve through toolbox
endpoints rather than reading local Markdown.

- [ ] **Step 10: Request code review**

Invoke `requesting-code-review` and ask the reviewer to focus on:

- lifecycle or scenario drift,
- packaging omissions,
- department-isolation regressions,
- hook ordering,
- removed tests or weakened assertions,
- duplicated or unnecessary new abstractions.

Address only high-confidence findings within scope.

- [ ] **Step 11: Commit documentation**

```bash
git add README.md AGENTS.md docs tests
git commit -m "docs: align lifecycle structure and deployment flow"
```

---

## Deferred Live Azure Verification

Run only with an approved Azure environment and operator confirmation:

```bash
azd provision --no-prompt
azd deploy --no-prompt
```

Verify:

1. `postprovision` creates four knowledge bases and three toolboxes in dependency order.
2. `TOOLBOX_ENDPOINT_*` values exist before agent deployment.
3. All three services start from `agent.py` with their assigned `DEPARTMENT`.
4. `postdeploy` grants only shared plus same-department Search access.
5. Continuous evaluation rules are created or updated without duplication.
6. Smoke invocations, deployment gate evaluation, and Operate verification preserve their current
   outputs and failure behavior.

Do not describe live deployment as verified until these checks complete.

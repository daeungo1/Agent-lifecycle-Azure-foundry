# Lifecycle Repository Structure Refactor

## Purpose

Restore the repository to the structure its own design document already specifies, and remove the
duplication that makes department changes expensive. The current tree hides the Build -> Evaluate ->
Operate lifecycle, ships operational tooling into the production agent runtime, and repeats the
department roster in thirteen places. This refactor reorganizes the tree, introduces a single source
of truth for department-derived names, and moves post-provision work into `azd` hooks.

Agent behavior, evaluation thresholds, RBAC boundaries, and the deployed Azure topology stay
unchanged. This is a structural refactor, not a functional one.

## Problem Statement

### Finding 1: The department roster is duplicated in thirteen places

`departments.yaml` is the intended source of truth, but only four files read it. Every other consumer
hardcodes its own copy of the roster or a name derived from it:

| Location | Duplicated content |
| --- | --- |
| `src/lifecycle_agent/config.py` | `ALLOWED_DEPARTMENTS` tuple |
| `scripts/toolbox_ops.py` | Toolbox spec map, boundary-to-env-suffix map |
| `scripts/set_agent_rbac.py` | Agent-to-department map, `KNOWN_BOUNDARIES`, env suffix map |
| `scripts/provision_knowledge_bases.py` | Knowledge path map, index short-name map |
| `scripts/configure_continuous_evaluation.py` | `DEPARTMENT_AGENT_NAMES` map |
| `scripts/verify_deployment.py` | Agent-to-department map |
| `scripts/agent365/verify_registry.py` | `AGENT_NAMES` list, per-department CLI arguments |
| `evals/validate_dataset.py` | Department keyword map |
| `scripts/configure_toolboxes.ps1` | Hardcoded per-department invocations |
| `azure.yaml` | Three near-identical service blocks |
| `infra/main.bicep` | Four copied Search module blocks |
| `toolboxes/*.yaml` | Three files |
| `services/agents/*/main.py` | Three byte-identical shims |

Adding a fourth department currently requires editing thirteen locations.

### Finding 2: Operational tooling ships into the production agent runtime

`.agentignore` excludes `evals/`, `infra/`, `tests/`, and `toolboxes/`, but not `scripts/`. With
`dependencyResolution: remote_build`, roughly 2,500 lines of Azure CLI wrappers and `httpx`
provisioning code are packaged into each hosted agent.

`requirements.txt` is a single flat file, so `pytest`, `ruff`, `debugpy`, and `Pillow` are installed
into the production runtime. `Pillow` exists solely for `scripts/render-excalidraw.py`, a
documentation image generator.

### Finding 3: `services/agents/*/main.py` are three byte-identical files

All three files hash to `2034aea295e0655a0aa83a9e9b055fa0`. They contain no department-specific
content; the department is supplied entirely through the `DEPARTMENT` environment variable, which
`azure.yaml` already injects per service. The directory exists only to give each service a distinct
`entryPoint` path, and each copy performs its own `sys.path` manipulation.

### Finding 4: `scripts/` mixes four unrelated categories

Paths below are relative to `scripts/` unless stated otherwise.

| Category | Files | Characteristics |
| --- | --- | --- |
| Provisioning (mutating) | `provision_knowledge_bases.py`, `configure_toolboxes.ps1`, `set_agent_rbac.py`, `configure_continuous_evaluation.py` | Change Azure state, strict ordering |
| Verification (read-only) | `verify_deployment.py`, `validate_eval_results.py`, `agent365/verify_registry.py`, `agent365/configure_observability.py` | Exit non-zero on failure |
| Pure logic libraries | `toolbox_ops.py`, and `evals/validate_dataset.py` outside this directory | No side effects, consumed by tests |
| Developer tooling | `render-excalidraw.py` | Unrelated to deployment |

The last row shows that the split is not even contained within one directory: two pure logic
libraries with the same character live in two different trees.

Two additional defects sit inside this mix:

- `agent365/configure_observability.py` configures nothing. It inspects installed package metadata
  and prints a readiness status. The name is wrong.
- `scripts/verify_environment.ps1` is never invoked from any workflow, script, or test. It is dead
  code referenced only by a 2026-08-02 plan document.

### Finding 5: Toolbox logic exists twice

`scripts/toolbox_ops.py` (329 lines) holds toolbox specs, boundary rules, and `azd` command
construction as pure, tested Python. `scripts/configure_toolboxes.ps1` (508 lines) reimplements the
same logic in PowerShell and is the component actually executed. The two are kept in sync by hand,
and the PowerShell dependency blocks cross-platform hook adoption.

### Finding 6: Post-provision hooks were specified but never built

`docs/superpowers/specs/2026-08-02-agent-lifecycle-design.md` line 44 states: "Post-provision hooks
create four Foundry IQ knowledge bases and their MCP connections." No `hooks` section exists in
`azure.yaml`. The deployment workflow assembles the sequence manually instead, and local
reproduction requires running six commands in the correct order by hand.

### Finding 7: The design document records an impossible deployment order

Lines 165-166 of the same design document specify:

> 4. Run `azd provision` and `azd deploy` non-interactively.
> 5. Create or update the four Foundry IQ knowledge bases and three department toolboxes.

This order cannot work. `azure.yaml` injects `${TOOLBOX_ENDPOINT_DEVELOPMENT}` and its siblings into
the agents as environment variables, so the toolboxes must exist before `azd deploy`. The workflow
implements the correct order; the specification is wrong.

## Measured Dependency Chain

The ordering below is enforced by data flow, not convention. It is the most important piece of
domain knowledge in the repository and is currently encoded only as the step order of a YAML
workflow file.

```
azd provision
  produces: four Search endpoints
        |
provision_knowledge_bases.py
  reads:    Search endpoints
  writes:   KB_MCP_ENDPOINT_{SHARED,DEVELOPMENT,HUMAN_RESOURCES,MARKETING}   (azd env set)
        |
configure_toolboxes.ps1
  reads:    KB_MCP_ENDPOINT_*
  writes:   TOOLBOX_ENDPOINT_{DEVELOPMENT,HUMAN_RESOURCES,MARKETING}         (azd env set)
        |
azd deploy
  reads:    TOOLBOX_ENDPOINT_* through azure.yaml environmentVariables
  produces: three hosted agent managed identities
        |
set_agent_rbac.py            requires agent identities
configure_continuous_evaluation.py   requires agent names to exist
```

Consequences:

- Knowledge bases and toolboxes belong in a `postprovision` hook. They must complete before deploy.
- RBAC and continuous evaluation cannot run in `postprovision`. The agent identities do not exist
  yet, so those steps would fail deterministically. They belong in a `postdeploy` hook.

## Evaluation Model

"Evaluation" in this repository refers to three distinct loops. The current structure does not
distinguish them, which is the source of the ambiguity about whether evaluation is a deploy-time or
a continuous activity.

| Loop | Trigger | Data | Evaluators | Blocking | Cost profile |
| --- | --- | --- | --- | --- | --- |
| 1. Dataset validation | Every push and pull request | Local JSONL files | Schema and boundary rules | Yes, in CI | Zero, no Azure access |
| 2. Deployment gate | Once per deployment | Fixed golden datasets in `evals/data` | 5: intent_resolution, task_adherence, relevance, tool_call_accuracy, groundedness | Yes, blocks promotion | Bounded, one run per deploy |
| 3. Continuous evaluation | Continuous, server-side | Sampled production response traffic | 3: intent_resolution, task_adherence, relevance | No, signal only | Capped at 20 runs per hour |

`configure_continuous_evaluation.py` does not run evaluations. It registers a
`RESPONSE_COMPLETED` rule with Foundry using a deterministic rule id and `create_or_update`, so it
is idempotent declarative configuration rather than an evaluation execution. Loop 3 feeds loop 2
through the trace-to-regression promotion procedure in `docs/operations.md`.

The evaluator sets for loops 2 and 3 are hardcoded independently in `eval.yaml` and
`configure_continuous_evaluation.py`. The reduction from five to three evaluators is undocumented.
This refactor records the rationale in `docs/operations.md` but does not change either set.

## Target Structure

```
Agent-lifecycle-Azure-foundry/
|
|-- agent.py                    Single hosted agent entry point, shared by all three services
|-- azure.yaml                  azd entry point, must remain at the repository root
|-- departments.yaml            Domain source of truth
|-- pyproject.toml
|-- requirements.txt            Runtime dependencies only
|-- requirements-ops.txt        Deployment hook dependencies
|-- requirements-dev.txt        Test and documentation dependencies
|-- README.md / AGENTS.md / .agentignore / .env.example / .gitignore
|
|-- deploy/                     Build-phase assets
|   |-- hooks/
|   |   |-- postprovision.sh
|   |   |-- postprovision.ps1
|   |   |-- postdeploy.sh
|   |   `-- postdeploy.ps1
|   |-- infra/
|   |   |-- main.bicep
|   |   |-- main.bicepparam
|   |   |-- abbreviations.json
|   |   `-- modules/
|   `-- toolboxes/
|       |-- development.yaml
|       |-- human-resources.yaml
|       `-- marketing.yaml
|
|-- evals/                      Evaluate-phase assets
|   |-- eval.yaml
|   `-- data/*.jsonl
|
|-- knowledge/                  Indexed corpus only
|   `-- {shared,development,human-resources,marketing}/*.md
|
|-- src/
|   |-- lifecycle_agent/        Shipped to Azure
|   |   |-- host.py
|   |   |-- settings.py
|   |   |-- departments.py
|   |   |-- orchestration.py
|   |   |-- toolbox.py
|   |   |-- observability.py
|   |   `-- prompts/*.md
|   `-- lifecycle_ops/          Never shipped to Azure
|       |-- naming.py
|       |-- azd_env.py
|       |-- provisioning/
|       |   |-- knowledge_bases.py
|       |   |-- toolboxes.py
|       |   |-- rbac.py
|       |   `-- continuous_eval.py
|       |-- evaluation/
|       |   |-- dataset.py
|       |   `-- gate.py
|       `-- operations/
|           |-- deployment_check.py
|           `-- agent365/
|               |-- readiness.py
|               `-- registry.py
|
|-- tests/
|   |-- agent/                  lifecycle_agent tests
|   |-- ops/                    provisioning, evaluation, operations tests
|   `-- repo/                   hook parity, infra, workflow, documentation contracts
|
`-- docs/
    |-- architecture/
    |-- tools/render_excalidraw.py
    |-- operations.md
    |-- identity-and-access.md
    `-- superpowers/{specs,plans}/
```

Deleted: `scripts/` and `services/` in their entirety, including `verify_environment.ps1` (dead
code) and `configure_toolboxes.ps1` (absorbed into `lifecycle_ops/provisioning/toolboxes.py`).

Top-level directories drop from nine to six. Top-level YAML files drop from three to two, leaving
`azure.yaml` as the deployment entry point and `departments.yaml` as the domain source of truth.

### File movement map

| From | To |
| --- | --- |
| `src/lifecycle_agent/main.py` | `src/lifecycle_agent/host.py` |
| `src/lifecycle_agent/config.py` | Split into `settings.py` and `departments.py` |
| `services/agents/*/main.py` | Deleted, replaced by root `agent.py` |
| `scripts/provision_knowledge_bases.py` | `src/lifecycle_ops/provisioning/knowledge_bases.py` |
| `scripts/toolbox_ops.py` + `scripts/configure_toolboxes.ps1` | `src/lifecycle_ops/provisioning/toolboxes.py` |
| `scripts/set_agent_rbac.py` | `src/lifecycle_ops/provisioning/rbac.py` |
| `scripts/configure_continuous_evaluation.py` | `src/lifecycle_ops/provisioning/continuous_eval.py` |
| `evals/validate_dataset.py` | `src/lifecycle_ops/evaluation/dataset.py` |
| `evals/__init__.py` | Deleted, `evals/` becomes a data-only directory |
| `scripts/validate_eval_results.py` | `src/lifecycle_ops/evaluation/gate.py` |
| `scripts/verify_deployment.py` | `src/lifecycle_ops/operations/deployment_check.py` |
| `scripts/agent365/configure_observability.py` | `src/lifecycle_ops/operations/agent365/readiness.py` |
| `scripts/agent365/verify_registry.py` | `src/lifecycle_ops/operations/agent365/registry.py` |
| `scripts/render-excalidraw.py` | `docs/tools/render_excalidraw.py` |
| `scripts/verify_environment.ps1` | Deleted |
| `infra/` | `deploy/infra/` |
| `toolboxes/` | `deploy/toolboxes/` |
| `eval.yaml` | `evals/eval.yaml` |

## Design Decisions

### Root entry point instead of a package-internal entry point

A hosted agent `entryPoint` must be runnable as a script. Modules inside `lifecycle_agent` use
relative imports, and executing such a module directly raises
`ImportError: attempted relative import with no known parent package`. The entry point therefore
lives at the repository root and performs an absolute import:

```python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

if __name__ == "__main__":
    from lifecycle_agent.host import main

    main()
```

All three services point at this file. The department is already differentiated by the `DEPARTMENT`
environment variable in `azure.yaml`. This replaces three identical files at four levels of nesting
with one named file at the root, and reduces `sys.path` manipulation from three sites to one.

### Two packages instead of one

`lifecycle_agent` contains only what runs inside the hosted agent. `lifecycle_ops` contains
provisioning, evaluation, and operations tooling and is excluded from the agent package through
`.agentignore`. The split is what allows `requirements.txt` to shrink to runtime dependencies.
`requirements-ops.txt` adds deployment-only dependencies such as `httpx`, while
`requirements-dev.txt` extends the ops environment with `pytest`, `ruff`, `debugpy`, and `Pillow`.
This three-way split is required because local `azd provision` executes ops hooks without needing
the full test and documentation toolchain.

### Hooks as thin shells at `deploy/hooks/`

`deploy/hooks/postprovision.sh` in full:

```sh
#!/bin/sh
set -eu
export PYTHONPATH="${PWD}/src${PYTHONPATH:+:${PYTHONPATH}}"
python -m lifecycle_ops.provisioning.knowledge_bases
python -m lifecycle_ops.provisioning.toolboxes
```

`deploy/hooks/postdeploy.sh` in full:

```sh
#!/bin/sh
set -eu
export PYTHONPATH="${PWD}/src${PYTHONPATH:+:${PYTHONPATH}}"
python -m lifecycle_ops.provisioning.rbac
python -m lifecycle_ops.provisioning.continuous_eval
```

The `.ps1` variants set `$ErrorActionPreference = 'Stop'`, add `src` to `PYTHONPATH`, and invoke the
same two modules in the same order. The scripts contain only import-path setup and module
invocations, so the cost of maintaining both variants is limited to keeping the module sequence
identical, which `tests/repo/test_hooks_contract.py` enforces.

`azure.yaml` declares:

```yaml
infra:
  provider: microsoft.foundry
  path: deploy/infra

hooks:
  postprovision:
    posix:   { shell: sh,   run: ./deploy/hooks/postprovision.sh }
    windows: { shell: pwsh, run: ./deploy/hooks/postprovision.ps1 }
  postdeploy:
    posix:   { shell: sh,   run: ./deploy/hooks/postdeploy.sh }
    windows: { shell: pwsh, run: ./deploy/hooks/postdeploy.ps1 }
```

### `departments.yaml` stays at the repository root

Four consumers read it: `lifecycle_agent`, `lifecycle_ops`, `deploy/infra` parameters, and the
evaluation dataset validator. Placing it under any one consumer implies ownership by that consumer.
It does not belong in `knowledge/`, which is scanned directory-by-directory and indexed into Azure
AI Search; a non-corpus file there would either be indexed or require an exclusion rule.
`knowledge/` also carries four boundaries including `shared`, while `departments.yaml` declares
three departments, so the two have different cardinality and represent different concepts.

### `naming.py` as the derivation point

All names derived from a department move into one module: agent name, environment variable suffix,
Search index name, knowledge directory, toolbox name, toolbox file path, continuous evaluation rule
id, and evaluation name. Every consumer imports from here instead of holding a private map.

### `azd_env.py` as the shared azd interface

`azd env get-values` and `azd env set` are currently invoked from four modules, each with its own
subprocess handling and parsing. They consolidate into one wrapper.

## Out of Scope

- **Bicep loop conversion.** `infra/main.bicep` emits named outputs such as
  `FOUNDRYIQ_SEARCH_ENDPOINT_SHARED` that downstream scripts read as `azd` environment variables.
  Converting the four Search modules to a loop risks changing those output names and breaking the
  environment contract. The four blocks stay as they are. This may be revisited separately once the
  output names can be verified as preserved.
- **Agent behavior, prompts, specialists, and orchestration logic.**
- **Evaluation thresholds, evaluator sets, and dataset contents.**
- **RBAC role definitions and boundary rules.**
- **Azure resource topology.**
- **`.foundry/` and `.vscode/` directories.** These appear in the 2026-08-02 design document but
  were never implemented. They are removed from that document rather than built here.

## Risk Register

| # | Risk | Severity | Mitigation |
| --- | --- | --- | --- |
| 1 | A package-internal `entryPoint` breaks relative imports and prevents all three agents from starting | Critical | Root `agent.py` bootstrap with absolute import |
| 2 | Bicep loop conversion renames `azd` environment outputs and breaks downstream scripts | High | Excluded from scope; `infra/main.bicep` content is moved but not rewritten |
| 3 | The PowerShell to Python toolbox merge cannot be fully verified without a live Azure environment | Medium | Write a command-sequence equivalence test before deleting the `.ps1`; the Python side already generates `azd` command lists under test |
| 4 | Moving `eval.yaml` may change how `dataset.local_uri` resolves | Medium | Keep the root-relative value unchanged and add a repository contract test proving every configured dataset path exists; do not change gate logic |
| 5 | `azd` hook behavior with the `microsoft.foundry` infra provider is unverified | Medium | CI keeps explicit `azd provision` and `azd deploy` rather than adopting `azd up`; hooks fire on each command independently |
| 6 | `test_hosted_agent_packaging.py` reads `environmentVariables[1]` by position | Low | Replace with name-based lookup |
| 7 | `test_hosted_agent_services_use_root_project_and_nested_entrypoints` encodes the current nested layout | Low | Rewrite to assert the shared entry point; rename accordingly |
| 8 | Six test files hold path constants for `scripts/`, `infra/`, and `evals/` | Low | Update paths within the same step as each move |
| 9 | `departments.yaml` discovery uses a fixed `parents[2]` offset | Low | Replace with an upward search for the file |
| 10 | Splitting requirements may leave CI without ops or test dependencies | Low | CI installs both files |

## Implementation Phases

Each phase leaves the repository in a working, testable state.

**P0 — Baseline.** Create the branch and record a full `pytest -v` and `ruff check .` baseline.

This phase requires a working Python 3.13 environment with `requirements.txt` installed. The
baseline test count and pass state must be recorded before any file moves, because acceptance
criterion 1 compares against it. If the environment cannot provide Python 3.13, the refactor should
not begin: every later phase depends on the test suite as its safety net.

**P1 — Packaging normalization.** Add root `agent.py`. Delete `services/`. Rename
`lifecycle_agent/main.py` to `host.py`. Split `config.py` into `settings.py` and `departments.py`,
replacing the `parents[2]` root discovery with an upward search. Set pytest `pythonpath = ["src"]`.
Update `azure.yaml` entry points. Rewrite the two affected packaging tests.

**P2 — Ops package.** Create `src/lifecycle_ops/` with `naming.py` and `azd_env.py`. Move the eight
operational modules. Replace every hardcoded department map with `naming.py` derivations. Move tests
into `tests/agent/`, `tests/ops/`, and `tests/repo/`.

**P3 — Toolbox consolidation.** Write the command-sequence equivalence test between
`configure_toolboxes.ps1` and the Python implementation. Complete
`lifecycle_ops/provisioning/toolboxes.py`. Delete the PowerShell script once the test passes.

**P4 — Deploy assets and hooks.** Create `deploy/` and move `infra/` and `toolboxes/` into it. Add
the four hook scripts. Update `azure.yaml` with `infra.path` and the `hooks` section. Add
`tests/repo/test_hooks_contract.py`. Reduce the deployment workflow accordingly.

**P5 — Evaluation and dependency assets.** Move `eval.yaml` to `evals/`. Add a static contract test
that resolves configured dataset paths from the repository root. Split `requirements.txt`,
`requirements-ops.txt`, and `requirements-dev.txt`. Move the renderer to `docs/tools/`. Update
`.agentignore` and CI installation steps.

**P6 — Documentation.** Correct the deployment order and repository layout in the 2026-08-02 design
document, remove its unimplemented `.foundry/` and `.vscode/` entries and the unimplemented
continuous-evaluation verification step. Rewrite the README deployment section. Record the
five-versus-three evaluator rationale in `docs/operations.md`. Update `AGENTS.md`.

## Testing and Acceptance

New tests:

- `tests/repo/test_hooks_contract.py`
  - `postprovision.sh` and `postprovision.ps1` invoke the same modules in the same order.
  - `postdeploy.sh` and `postdeploy.ps1` invoke the same modules in the same order.
  - `postprovision` invokes `knowledge_bases` before `toolboxes`.
  - `postprovision` invokes neither `rbac` nor `continuous_eval`, because agent identities do not
    exist at that point.
  - Every hook path named in `azure.yaml` exists on disk.
- `tests/ops/test_naming.py`
  - Every derived name is produced from `departments.yaml`, and no module holds a private roster.
- `tests/ops/test_toolbox_command_parity.py` (temporary, P3)
  - The Python implementation emits the same `azd` command sequence as the PowerShell script.
- `tests/repo/test_eval_config_contract.py`
  - Every configured dataset path resolves from the repository root and includes JSONL files.

Acceptance criteria:

1. `ruff check .` and `pytest -v` pass with no fewer tests than the P0 baseline.
2. `python agent.py` starts a department agent locally for all three `DEPARTMENT` values.
3. No Python module outside `src/lifecycle_agent/departments.py` and `src/lifecycle_ops/naming.py`
   contains a literal department roster. Declarative files that legitimately enumerate departments
   remain: `departments.yaml`, `azure.yaml` service blocks, `deploy/toolboxes/*.yaml`, and
   `deploy/infra/main.bicep`.
4. `scripts/` and `services/` no longer exist.
5. `requirements.txt` contains no deployment, test, lint, debug, or imaging dependency;
   `requirements-ops.txt` contains no test, lint, debug, or imaging dependency.
6. `.agentignore` excludes `src/lifecycle_ops/`, `deploy/`, `docs/`, `tests/`, `evals/`, and
   `knowledge/`.
7. `az bicep build --file deploy/infra/main.bicep` succeeds.
8. The deployment workflow contains no manual knowledge-base, toolbox, RBAC, or continuous
   evaluation step; those run through hooks.
9. The 2026-08-02 design document describes the actual deployment order and the actual layout.

Deferred verification: a live `azd provision` and `azd deploy` against an Azure environment
validates hook execution, `infra.path` resolution, `eval.yaml` dataset resolution, and shared
entry-point startup. Static contract tests are the safety net until that run happens.

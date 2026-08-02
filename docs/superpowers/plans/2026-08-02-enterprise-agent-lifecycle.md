# Enterprise Agent Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, evaluate, deploy, govern, and continuously operate three department-scoped Microsoft Foundry Hosted Agent systems grounded in isolated Foundry IQ knowledge bases.

**Architecture:** One Foundry project hosts three Python Responses 2.0 Hosted Agent services. Each service contains a coordinator and two specialist agents, consumes one department toolbox, and receives a distinct instance identity. Four Azure AI Search services form the shared and department knowledge security boundaries; Agent 365 adds conditional registry and observability integration without becoming the runtime authorization layer.

**Tech Stack:** Python 3.13, Microsoft Agent Framework, Foundry Hosted Agents, Foundry Toolbox, Foundry IQ/Azure AI Search, Azure Developer CLI, Bicep, Azure AI Projects SDK 2.x, OpenTelemetry/Application Insights, Microsoft Agent 365 observability, Pytest, Ruff, GitHub Actions OIDC, Excalidraw.

## Global Constraints

- The lifecycle order is always Build -> Evaluate -> Operate; infrastructure features must support one of those stages.
- Hosted Agent protocol is Responses version `2.0.0`.
- Hosted Agent runtime is `python_3_13`.
- The first model candidate is `gpt-5.4-mini` version `2026-03-17`, finalized only after subscription, region, catalog, and quota validation.
- Install Python dependencies from a version-pinned `requirements.txt`; the mandatory debug exception is `agent-dev-cli>=0.0.1b260427` exactly.
- Set `ENABLE_INSTRUMENTATION=true` and `ENABLE_SENSITIVE_DATA=false` for every deployed agent.
- Use `DefaultAzureCredential`, managed identities, GitHub OIDC, and Toolbox connections; never store Azure API keys or raw OBO tokens in source, prompts, logs, or agent caches.
- Provision one shared Search service and one Search service per department as intentional authorization boundaries.
- A department Agent Identity receives Search read access only to the shared Search service and its own department Search service.
- Agent 365 live export is conditional on tenant licensing and administrator enablement; lack of prerequisites must produce an explicit skipped result, not a false failure.
- The README must embed a rendered PNG and link to the editable `.excalidraw` source.

## File Map

- `src/lifecycle_agent/config.py`: typed environment and department configuration.
- `src/lifecycle_agent/orchestration.py`: specialist creation and coordinator-as-owner composition.
- `src/lifecycle_agent/toolbox.py`: authenticated MCP toolbox client construction.
- `src/lifecycle_agent/observability.py`: Foundry and optional Agent 365 instrumentation.
- `src/lifecycle_agent/main.py`: Responses host entry point selected by `DEPARTMENT`.
- `departments.yaml`: names, descriptions, prompts, toolbox env names, and specialists for all departments.
- `knowledge/**`: synthetic shared and private Markdown source documents.
- `scripts/provision_knowledge_bases.py`: idempotent Search index, knowledge source, and knowledge base provisioning.
- `scripts/set_agent_rbac.py`: idempotent per-agent Search role assignments.
- `scripts/configure_continuous_evaluation.py`: one response-completed evaluation rule per department agent.
- `scripts/agent365/configure_observability.py`: permission and configuration checks for Agent 365 export.
- `scripts/agent365/verify_registry.py`: verified or prerequisite-skipped registry status.
- `evals/validate_dataset.py`: JSONL schema and department-boundary validation.
- `eval.yaml`: shared Foundry evaluation intent.
- `evals/data/*.jsonl`: department, grounding, and authorization test cases.
- `infra/**`: Foundry, Search, identity, and monitoring Bicep modules.
- `toolboxes/*.yaml`: two-knowledge-base toolbox definitions for each department.
- `.github/workflows/ci.yml`: local Build and evaluation-contract checks.
- `.github/workflows/deploy-evaluate.yml`: OIDC deploy, smoke, evaluation gate, and Operate verification.
- `docs/architecture/enterprise-agent-lifecycle.{excalidraw,png}`: editable and rendered architecture.

---

### Task 1: Build Foundation And Typed Configuration

**Files:**
- Create: `.gitignore`, `.env.example`, `requirements.txt`, `pyproject.toml`, `AGENTS.md`, `.agentignore`
- Create: `src/lifecycle_agent/__init__.py`, `src/lifecycle_agent/config.py`, `departments.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `DepartmentConfig`, `SpecialistConfig`, `Settings.from_env()`, `load_departments(path)` and `select_department(configs, name)`.
- Consumes: environment variables `DEPARTMENT`, `FOUNDRY_PROJECT_ENDPOINT`, `AZURE_AI_MODEL_DEPLOYMENT_NAME`, and `TOOLBOX_ENDPOINT`.

- [ ] **Step 1: Create the failing configuration tests**

Test that exactly `development`, `human-resources`, and `marketing` load; each has two specialists; unknown departments raise `ValueError`; and missing runtime variables raise a single message listing all absent names.

- [ ] **Step 2: Verify the tests fail**

Run: `python -m pytest tests/test_config.py -v`

Expected: collection fails because `src.lifecycle_agent.config` does not exist.

- [ ] **Step 3: Install and pin dependencies**

Create `.venv`, install the current official packages with prereleases enabled only where required, and write exact resolved versions to `requirements.txt`. Preserve these mandatory lower-bound lines verbatim:

```text
agent-framework-foundry-hosting>=1.0.0a260630
agent-dev-cli>=0.0.1b260427
```

Include Agent Framework Foundry, Azure AI Projects, Azure Identity, python-dotenv, httpx, PyYAML, Pytest, Ruff, debugpy, Pillow, and Agent 365 observability packages.

- [ ] **Step 4: Implement typed configuration**

Use frozen dataclasses, validate the department allow-list, resolve prompts relative to the repository root, and keep credentials out of configuration objects.

- [ ] **Step 5: Run Build checks**

Run: `python -m pytest tests/test_config.py -v && python -m ruff check src tests scripts evals`

Expected: all configuration tests pass and Ruff reports no errors.

- [ ] **Step 6: Commit**

Commit message: `build: add typed enterprise agent configuration`

### Task 2: Build Department Multi-Agent Services

**Files:**
- Create: `src/lifecycle_agent/toolbox.py`, `src/lifecycle_agent/orchestration.py`, `src/lifecycle_agent/observability.py`, `src/lifecycle_agent/main.py`
- Create: `src/lifecycle_agent/prompts/development.md`, `src/lifecycle_agent/prompts/human-resources.md`, `src/lifecycle_agent/prompts/marketing.md`
- Test: `tests/test_orchestration.py`, `tests/test_observability.py`

**Interfaces:**
- Consumes: `DepartmentConfig` and `Settings` from Task 1.
- Produces: `build_department_agent(config, settings, credential) -> Agent`, `build_toolbox(endpoint, credential) -> MCPStreamableHTTPTool`, and `configure_observability(department) -> None`.

- [ ] **Step 1: Write failing orchestration tests**

Mock `FoundryChatClient`, `Agent`, and `MCPStreamableHTTPTool`. Assert two specialists become tools via `as_tool()`, the coordinator retains ownership, the toolbox is attached once, and `default_options == {"store": False}`.

- [ ] **Step 2: Verify focused failure**

Run: `python -m pytest tests/test_orchestration.py tests/test_observability.py -v`

Expected: failures identify missing build and instrumentation functions.

- [ ] **Step 3: Implement specialist-as-tool orchestration**

Create two stateless specialist `Agent` instances per department, convert them with `as_tool(name=..., description=...)`, attach the department MCP toolbox, and host only the coordinator with `ResponsesHostServer`.

- [ ] **Step 4: Implement safe observability**

Use Agent Framework automatic OpenTelemetry instrumentation. Configure Agent 365 only when `ENABLE_A365_OBSERVABILITY_EXPORTER=true`; set suppression of invocation input by default and provide console output when service export is disabled.

- [ ] **Step 5: Run Build checks**

Run: `python -m pytest tests/test_orchestration.py tests/test_observability.py -v && python -m ruff check src tests`

Expected: all tests pass and no lint errors remain.

- [ ] **Step 6: Commit**

Commit message: `feat: build department multi-agent hosts`

### Task 3: Evaluate Contracts And Security Boundaries

**Files:**
- Create: `evals/validate_dataset.py`, `evals/data/development.jsonl`, `evals/data/human-resources.jsonl`, `evals/data/marketing.jsonl`, `evals/data/regression.jsonl`, `evals/data/security-boundaries.jsonl`, `eval.yaml`
- Test: `tests/test_eval_datasets.py`

**Interfaces:**
- Produces: `validate_record(record, source)`, `validate_dataset(path)`, and a JSON summary consumable by CI.
- Dataset fields: `department`, `query`, `expected_behavior`, `expected_tools`, `must_cite`, `forbidden_terms`.

- [ ] **Step 1: Write failing dataset tests**

Cover valid records, duplicate queries, absent expected behavior, unknown departments, empty tool lists, and cross-department cases without forbidden terms.

- [ ] **Step 2: Verify focused failure**

Run: `python -m pytest tests/test_eval_datasets.py -v`

Expected: import failure for `evals.validate_dataset`.

- [ ] **Step 3: Implement schema validation and seed datasets**

Create at least five normal cases per department, three shared-KB citation cases, and six negative cross-department cases. No seed answer may contain confidential or personal data.

- [ ] **Step 4: Define Foundry evaluation intent**

Set evaluators to intent resolution, task adherence, relevance, tool-call accuracy, and groundedness. Use a smoke tier before regression and set an initial pass threshold of `0.70` that can be calibrated from the first successful baseline.

- [ ] **Step 5: Run Evaluate contract checks**

Run: `python evals/validate_dataset.py evals/data && python -m pytest tests/test_eval_datasets.py -v`

Expected: JSON summary reports five files, all records valid, and nonzero security-boundary coverage.

- [ ] **Step 6: Commit**

Commit message: `test: add department lifecycle evaluation contracts`

### Task 4: Operate Foundry And Foundry IQ Infrastructure

**Files:**
- Create: `azure.yaml`, `infra/main.bicep`, `infra/main.parameters.json`, `infra/modules/search.bicep`
- Create: `knowledge/shared/company-handbook.md`, `knowledge/development/engineering-standards.md`, `knowledge/human-resources/people-policy.md`, `knowledge/marketing/brand-guidelines.md`
- Create: `scripts/provision_knowledge_bases.py`, `scripts/verify_environment.ps1`
- Test: `tests/test_knowledge_manifest.py`

**Interfaces:**
- Produces four Search endpoints, four knowledge base MCP endpoints, one Foundry project endpoint, and three Hosted Agent service definitions.
- Consumes model deployment and Azure location selected through the active `azd` environment.

- [ ] **Step 1: Write failing knowledge manifest tests**

Assert one shared plus three private knowledge roots, unique index/source/base names, no private document under shared, and all documents have a title and classification header.

- [ ] **Step 2: Verify focused failure**

Run: `python -m pytest tests/test_knowledge_manifest.py -v`

Expected: failures for missing knowledge roots and manifest.

- [ ] **Step 3: Implement Bicep and `azure.yaml`**

Define one Foundry project/model, three `azure.ai.agent` services using the same source with different `DEPARTMENT` and `TOOLBOX_ENDPOINT` values, Application Insights, and four Basic Search services with managed identity and RBAC API access.

- [ ] **Step 4: Implement idempotent Foundry IQ provisioning**

Use the Azure AI Search `2026-04-01` REST API for generally available index, knowledge source, and knowledge base operations. Derive deterministic names, upload synthetic documents, and store endpoints in the active `azd` environment without printing credentials.

- [ ] **Step 5: Validate infrastructure locally**

Run: `az bicep build --file infra/main.bicep` and `python -m pytest tests/test_knowledge_manifest.py -v`

Expected: Bicep build succeeds and all knowledge tests pass.

- [ ] **Step 6: Commit**

Commit message: `infra: provision isolated Foundry IQ knowledge bases`

### Task 5: Operate Toolboxes, Agent Identity RBAC, And OBO Extension

**Files:**
- Create: `toolboxes/development.yaml`, `toolboxes/human-resources.yaml`, `toolboxes/marketing.yaml`
- Create: `scripts/set_agent_rbac.py`, `scripts/configure_toolboxes.ps1`, `docs/identity-and-access.md`
- Test: `tests/test_toolbox_boundaries.py`

**Interfaces:**
- Produces one toolbox endpoint per department with exactly two knowledge tools.
- Produces an RBAC report mapping each Hosted Agent principal to shared plus one private Search service.
- Documents optional OAuth identity passthrough and why raw OBO token injection is prohibited.

- [ ] **Step 1: Write failing toolbox boundary tests**

Parse all toolbox YAML and assert each file references `shared` and only its own department connection. Reject duplicate server labels and any API key auth type.

- [ ] **Step 2: Verify focused failure**

Run: `python -m pytest tests/test_toolbox_boundaries.py -v`

Expected: missing toolbox definitions.

- [ ] **Step 3: Implement Agentic Identity toolboxes**

Create two MCP connections per department to the Foundry IQ knowledge base endpoints, configure Agentic Identity with the Search audience, and publish one immutable toolbox version per department.

- [ ] **Step 4: Implement least-privilege RBAC**

Resolve each deployed agent's instance principal ID and grant `Search Index Data Reader` only on shared plus matching Search service. Verify absence of cross-department assignments and emit machine-readable output.

- [ ] **Step 5: Add sustainable OBO path**

Document and template a Toolbox OAuth identity passthrough connection for a future ACL-aware MCP source. State the same-tenant and Foundry Agent Consumer requirements. Do not attach it to the synthetic Foundry IQ path because that quickstart intentionally requires Agentic Identity.

- [ ] **Step 6: Run authorization tests**

Run: `python -m pytest tests/test_toolbox_boundaries.py -v`

Expected: all static authorization boundaries pass.

- [ ] **Step 7: Commit**

Commit message: `security: isolate department knowledge access`

### Task 6: Operate Continuous Evaluation And Agent 365

**Files:**
- Create: `scripts/configure_continuous_evaluation.py`, `scripts/agent365/configure_observability.py`, `scripts/agent365/verify_registry.py`, `docs/operations.md`
- Test: `tests/test_continuous_eval.py`, `tests/test_agent365_status.py`

**Interfaces:**
- Produces three enabled response-completed evaluation rules with bounded hourly runs.
- Produces Agent 365 status values `verified`, `prerequisite-skipped`, or `failed` with actionable details.

- [ ] **Step 1: Write failing lifecycle operation tests**

Mock `AIProjectClient` and test idempotent rule names, department filters, maximum hourly runs, sensitive input suppression, and prerequisite-skipped behavior.

- [ ] **Step 2: Verify focused failure**

Run: `python -m pytest tests/test_continuous_eval.py tests/test_agent365_status.py -v`

Expected: missing operation modules.

- [ ] **Step 3: Implement continuous evaluation**

Create or reuse evaluation definitions and `EvaluationRule` objects for all deployed department agent names. Do not create prompt agents as a side effect.

- [ ] **Step 4: Implement Agent 365 observability readiness**

Resolve the Hosted Agent identity, check for the `Agent365Observability` service principal and `Agent365.Observability.OtelWrite` assignment, and configure the Python Agent Framework extension. Missing license/admin prerequisites return `prerequisite-skipped`.

- [ ] **Step 5: Write the Operate runbook**

Cover Foundry Monitor, Agent 365 registry, trace-to-regression promotion, access reviews, version rollback, continuous-evaluation limits, data residency, and teardown.

- [ ] **Step 6: Run Operate unit checks**

Run: `python -m pytest tests/test_continuous_eval.py tests/test_agent365_status.py -v`

Expected: all operation tests pass.

- [ ] **Step 7: Commit**

Commit message: `operate: add continuous evaluation and Agent 365 readiness`

### Task 7: Build-Evaluate-Operate CI/CD

**Files:**
- Create: `.github/workflows/ci.yml`, `.github/workflows/deploy-evaluate.yml`
- Create: `scripts/verify_deployment.py`
- Test: `tests/test_workflows.py`

**Interfaces:**
- CI produces Build and evaluation-contract evidence without Azure writes.
- Deployment produces agent status, smoke, evaluation, authorization, continuous-eval, and Agent 365 summaries.

- [ ] **Step 1: Write failing workflow tests**

Parse workflow YAML and assert OIDC permissions, pinned action majors, no client-secret references, Build before deploy, department smoke matrix, evaluation gate before Operate verification, and concurrency protection.

- [ ] **Step 2: Verify focused failure**

Run: `python -m pytest tests/test_workflows.py -v`

Expected: missing workflow files.

- [ ] **Step 3: Implement CI workflow**

Run pinned dependency installation, Ruff, Pytest, dataset validation, Bicep build, and YAML contract checks on pull requests and pushes.

- [ ] **Step 4: Implement deployment workflow**

Authenticate with GitHub OIDC, install `azd` and `microsoft.foundry`, run provision/deploy non-interactively, configure KB/toolboxes/RBAC, invoke every department, run evaluation gates, configure continuous evaluation, and report Agent 365 readiness.

- [ ] **Step 5: Run Build workflow tests**

Run: `python -m pytest tests/test_workflows.py -v && python -m ruff check .`

Expected: all workflow tests and lint checks pass.

- [ ] **Step 6: Commit**

Commit message: `ci: enforce enterprise agent lifecycle gates`

### Task 8: Excalidraw Architecture And README

**Files:**
- Create: `docs/architecture/enterprise-agent-lifecycle.excalidraw`, `docs/architecture/enterprise-agent-lifecycle.png`, `scripts/render-excalidraw.py`, `README.md`
- Test: `tests/test_documentation.py`

**Interfaces:**
- README embeds the PNG and links to the editable source.
- Diagram shows Build, Evaluate, Operate, three department agents, four KB boundaries, toolboxes, identity, GitHub Actions, App Insights, and Agent 365.

- [ ] **Step 1: Write failing documentation tests**

Assert the Excalidraw source is valid JSON with unique element IDs, all text uses one font family, PNG exists and is nonempty, README embeds it, and README contains the lifecycle commands.

- [ ] **Step 2: Verify focused failure**

Run: `python -m pytest tests/test_documentation.py -v`

Expected: architecture and README files are absent.

- [ ] **Step 3: Generate architecture source and PNG**

Use fewer than twenty high-level nodes, smooth gap-routed arrows, and English labels with Excalifont. Render with Pillow and inspect the PNG dimensions and nonblank pixel distribution.

- [ ] **Step 4: Write README**

Lead with the architecture image, explain Build-Evaluate-Operate, include prerequisites, local run, deployment, evaluation, Agent 365 conditional status, OBO decision, cost warning, and teardown.

- [ ] **Step 5: Run documentation checks**

Run: `python -m pytest tests/test_documentation.py -v`

Expected: source, render, and README checks pass.

- [ ] **Step 6: Commit**

Commit message: `docs: add enterprise lifecycle architecture and runbook`

### Task 9: Deploy, Verify, Create Private Repository, And Push

**Files:**
- Modify only files required by concrete validation failures.

**Interfaces:**
- Produces a live Azure demo environment and a private GitHub repository at `daeungo1/Agent-lifecycle-Azure-foundry`.

- [ ] **Step 1: Run complete local verification**

Run: `python -m ruff check .`, `python -m pytest -v`, `python evals/validate_dataset.py evals/data`, and `az bicep build --file infra/main.bicep`.

Expected: all commands exit zero.

- [ ] **Step 2: Verify Azure prerequisites**

Confirm `az`, `azd`, authentication, subscription, Owner/User Access Administrator permissions, Hosted Agent region support, model quota, Search availability, and Foundry extensions. Never initiate interactive login for the user.

- [ ] **Step 3: Provision and deploy**

Set `AZURE_DEV_USER_AGENT=microsoft_foundry_skill` inline for all `azd` commands. Provision the dedicated environment, deploy three agents, configure knowledge and access, and keep retry/fallback decisions in the run log.

- [ ] **Step 4: Execute remote lifecycle acceptance**

Verify three active agent versions, six permitted KB retrievals, cross-department denials, batch evaluation threshold, Application Insights traces, three continuous evaluation rules, and Agent 365 verified-or-skipped status.

- [ ] **Step 5: Create GitHub repository and OIDC configuration**

Create private repository `daeungo1/Agent-lifecycle-Azure-foundry`, add the remote, configure repository variables and federated credentials without long-lived secrets, and protect the deployment environment when supported.

- [ ] **Step 6: Push and verify**

Push `main`, verify the remote default branch, repository privacy, commit history, and workflow visibility. Do not claim success until the remote repository contains the final verified commit.

- [ ] **Step 7: Final commit when validation required changes**

Commit message: `fix: complete remote lifecycle validation`
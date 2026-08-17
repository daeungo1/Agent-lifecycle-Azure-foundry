# Agent Lifecycle on Microsoft Foundry

## Purpose

Build a reproducible enterprise demonstration repository for the full lifecycle of Microsoft Foundry Hosted Agents: build, evaluate, deploy, govern, observe, and continuously evaluate production traffic. The repository must provision an isolated demo environment, deploy department-scoped multi-agent systems, ground them in permission-aware knowledge bases, enforce a pre-release quality gate, and activate an operational evaluation loop.

## Scope

The demo includes:

- Three Python Hosted Agents built with Microsoft Agent Framework for Development, Human Resources, and Marketing.
- A coordinator and two specialist agents inside each department service.
- The OpenAI-compatible Responses protocol, version 2.0.0.
- Azure Developer CLI configuration for infrastructure and agent deployment.
- Local development, tests, and VS Code Agent Inspector debugging.
- A shared Foundry IQ knowledge base and three department-isolated Foundry IQ knowledge bases backed by Azure AI Search.
- A department-specific Foundry Toolbox that exposes only the shared and matching department knowledge bases.
- Per-agent managed identities and least-privilege Azure RBAC.
- Microsoft Agent 365 registry and observability integration that can be activated when tenant prerequisites are available.
- An OAuth identity passthrough design for user-delegated access without placing raw OBO tokens in agent code.
- Seed smoke and regression evaluation datasets.
- Batch evaluation and a deployment quality gate.
- Application Insights tracing and Foundry monitoring.
- A continuous evaluation rule for deployed agent responses.
- GitHub Actions authentication through OpenID Connect.
- A private GitHub repository named `Agent-lifecycle-Azure-foundry`.

The demo uses synthetic Markdown documents as its business data. It does not connect to a production HR system, source repository, marketing platform, SharePoint tenant, or other external business API. Agent 365 tenant activation and admin approval are conditional because the current tenant license and administrator readiness are unknown.

## Agent Scenario

Each department exposes one Hosted Agent service containing a coordinator and two specialists:

- Development: architecture and code-quality specialists.
- Human Resources: policy and onboarding specialists.
- Marketing: campaign and content specialists.

The coordinator retains task ownership and invokes specialists as tools. This pattern gives each department one stable endpoint and one identity while keeping specialist responsibilities independently testable. Department agents answer from a shared company knowledge base and their own department knowledge base, with citations. They must refuse or report lack of access when asked for another department's private material.

## Architecture

The three department agents run on the Microsoft Foundry Hosted Agent runtime. Microsoft Agent Framework supplies agent abstractions, `FoundryChatClient`, agents-as-tools orchestration, and automatic OpenTelemetry instrumentation. The Foundry hosting package exposes each department coordinator through the Responses protocol. The platform manages conversation history, streaming, runtime identity, and scale.

`azure.yaml` is the deployment source of truth. It defines a Foundry project service, a model deployment, three Hosted Agent services, and the deployment hooks. Bicep creates one shared Azure AI Search service and one isolated Search service per department. The `postprovision` hook creates four Foundry IQ knowledge bases, their MCP connections, and three department toolboxes. `azd provision` creates or updates the Azure resources. `azd deploy` publishes immutable department agent versions, after which the `postdeploy` hook applies RBAC. The deployment gate then runs before the Operate stage registers continuous evaluation rules. The first model candidate is `gpt-5.4-mini`, subject to subscription, region, quota, and catalog validation before provisioning.

Every department Hosted Agent receives a distinct instance identity. Its Azure RBAC grants read access to the shared Search service and only its matching department Search service. Separate Search services provide a real resource boundary rather than relying on connection names as a security control.

Each department toolbox exposes two `knowledge_base_retrieve` tools: shared knowledge and its department knowledge. The default authentication mode is Agentic Identity. User-delegated access is an optional connection mode implemented with Toolbox OAuth identity passthrough. Foundry handles consent, token exchange, isolation, refresh, and injection; raw OBO tokens never enter prompts, logs, source code, or agent-managed caches.

Published Foundry agents automatically synchronize to the Microsoft Agent 365 registry when the tenant is licensed and enabled. Hosted Agent activity export uses the Agent 365 observability extension and the `Agent365.Observability.OtelWrite` app role. Agent 365 is the governance and inventory control plane; Microsoft Entra Agent ID and Azure RBAC remain the enforcement plane.

Application Insights receives server-side Hosted Agent telemetry. Sensitive prompt and response content is not enabled by default. Foundry's monitoring dashboard surfaces latency, token usage, run success, and evaluation scores.

## Repository Layout

```text
.
|-- .github/
|   `-- workflows/
|       |-- ci.yml
|       `-- deploy-evaluate.yml
|-- deploy/
|   |-- hooks/
|   |   |-- postprovision.sh
|   |   |-- postprovision.ps1
|   |   |-- postdeploy.sh
|   |   `-- postdeploy.ps1
|   |-- infra/
|   |   |-- main.bicep
|   |   |-- main.bicepparam
|   |   `-- modules/
|   `-- toolboxes/
|       |-- development.yaml
|       |-- human-resources.yaml
|       `-- marketing.yaml
|-- docs/
|   |-- architecture/
|   |   |-- enterprise-agent-lifecycle.excalidraw
|   |   `-- enterprise-agent-lifecycle.png
|   |-- tools/
|   |   `-- render_excalidraw.py
|   |-- operations.md
|   `-- superpowers/
|       `-- specs/
|-- evals/
|   |-- eval.yaml
|   |-- data/
|   |   |-- development.jsonl
|   |   |-- human-resources.jsonl
|   |   |-- marketing.jsonl
|   |   |-- regression.jsonl
|   |   `-- security-boundaries.jsonl
|-- knowledge/
|   |-- shared/
|   |-- development/
|   |-- human-resources/
|   `-- marketing/
|-- src/
|   |-- lifecycle_agent/
|   |   |-- host.py
|   |   |-- settings.py
|   |   |-- departments.py
|   |   |-- orchestration.py
|   |   `-- prompts/
|   `-- lifecycle_ops/
|       |-- provisioning/
|       |-- evaluation/
|       `-- operations/
|-- tests/
|   |-- agent/
|   |-- ops/
|   `-- repo/
|-- agent.py
|-- departments.yaml
|-- .env.example
|-- .gitignore
|-- AGENTS.md
|-- azure.yaml
|-- pyproject.toml
|-- README.md
|-- requirements.txt
|-- requirements-ops.txt
`-- requirements-dev.txt
```

## Build Flow

1. Install the pinned development dependencies from `requirements-dev.txt` into a virtual environment.
2. Load the Foundry project endpoint and model deployment name from environment variables.
3. Select the department configuration from the `DEPARTMENT` environment variable.
4. Create two specialist agents and expose them as tools to the department coordinator.
5. Attach the department toolbox MCP endpoint to the coordinator.
6. Keep `store` disabled because the Hosted Agent Responses runtime owns conversation history.
7. Start the Responses server on port 8088 for local development.
8. Use Ruff and Pytest for fast local validation.

The implementation uses `DefaultAzureCredential`; it never accepts or stores an Azure API key.

## Evaluation Flow

The seed datasets use JSONL records with `query` and `expected_behavior`. The smoke suite is deliberately small and checks the highest-value behaviors before deployment. The regression suite provides broader lifecycle coverage and grows from reviewed production traces.

The initial evaluation dimensions are:

- Intent resolution.
- Task adherence.
- Response relevance.
- Tool-call accuracy.
- Groundedness and citation presence.
- Department authorization boundaries.

`evals/eval.yaml` defines the target agent, seed dataset, evaluators, maximum sample count, and passing threshold. CI runs the same recipe used locally. A failed threshold blocks the release workflow. Evaluation output is persisted as a workflow artifact; generated local results are ignored by Git unless explicitly curated.

## Deployment And CI/CD Flow

Pull requests run dependency installation, linting, unit tests, dataset validation, and configuration checks without modifying Azure resources.

A merge to `main` or a manual dispatch runs the deployment workflow:

1. Authenticate to Azure with GitHub OpenID Connect.
2. Install `azd` and the Foundry extensions.
3. Restore the named `azd` environment.
4. Run `azd provision` non-interactively.
5. The `postprovision` hook creates or updates the four Foundry IQ knowledge bases and three department toolboxes.
6. Run `azd deploy` non-interactively.
7. The `postdeploy` hook grants each Hosted Agent identity access to shared plus its matching department Search service.
8. Verify all three Hosted Agents reach an active state and invoke a representative smoke prompt for each department.
9. Run the deployment gate evaluation for department, grounding, and cross-department denial behavior and enforce its thresholds.
10. After the gate passes, register continuous evaluation rules in the Operate stage.
11. When Agent 365 prerequisites are present, verify registry visibility and observability readiness; otherwise emit an actionable skipped result.

The workflow identity receives only the roles required by provisioning, agent deployment, evaluation, and telemetry access. Repository variables hold non-secret identifiers. No long-lived client secret is used.

## Operate Flow

The first deployment connects Application Insights and enables server-side tracing. Operators use Foundry Monitor for latency, token usage, success rate, retrieval behavior, and evaluation trends. The continuous evaluation setup script creates one evaluation definition and enabled response-completed rule per deployed department agent, with bounded hourly run counts.

When enabled, Agent 365 receives identity-tagged activity through its OpenTelemetry integration. Administrators use the Agent 365 registry for inventory, ownership, lifecycle controls, and access reviews. The integration suppresses sensitive invocation input by default. Agent 365 data residency follows the Entra tenant and is documented separately from Foundry's Azure-region residency.

Production traces form the feedback loop:

1. Review low-scoring or failed interactions in Foundry Monitor and Application Insights.
2. Curate representative traces into a versioned regression dataset.
3. Reproduce the issue in the local and CI evaluation recipe.
4. Update the prompt or implementation.
5. Deploy a new immutable agent version.
6. Re-run the same evaluation suite and compare results.

Trace data is treated as production telemetry. Access follows Azure RBAC and retention follows the connected Application Insights configuration.

## Error Handling

Configuration loading fails fast with a clear message when required environment variables are absent. The Hosted Agent remains stateless with respect to deployment configuration. CI commands are non-interactive and fail rather than wait for input. Deployment verification distinguishes provisioning, deployment, invocation, evaluation, and continuous-evaluation failures so that the failed lifecycle stage is visible in the workflow summary.

Azure preview capabilities are explicitly identified in documentation. The runbook includes authentication recovery, quota and regional model fallback, deployment rollback by agent version, and resource teardown with `azd down`.

## Testing And Acceptance

The repository is complete when all of the following are demonstrated:

- Python syntax, lint, and unit tests pass.
- Evaluation datasets pass schema validation.
- The local Hosted Agent starts successfully when Foundry configuration is supplied.
- The dedicated Azure environment provisions successfully.
- Four Search services and four Foundry IQ knowledge bases are created and queryable.
- Three department toolboxes expose only their shared and matching private knowledge tools.
- All three Hosted Agents deploy and reach an active state.
- Remote smoke invocations return valid, cited responses for all departments.
- Cross-department private knowledge checks are denied or return no restricted content.
- The initial department and security batch evaluations complete and meet configured thresholds.
- Application Insights receives Hosted Agent telemetry.
- Continuous evaluation rules exist, are enabled, and target all deployed department agents.
- Agent 365 integration reports either verified registry/telemetry status or a precise prerequisite-skipped status.
- The README renders the Excalidraw architecture PNG and links to its editable source.
- The private GitHub repository contains the verified implementation and workflows.

## Operational Constraints

- Azure and Foundry authentication remain user-owned interactive steps. Automation uses existing authenticated sessions or workload identity.
- The chosen model and region must be validated against the user's subscription before provisioning.
- Continuous evaluation and some `azd ai agent eval` features are preview capabilities and are not represented as generally available production guarantees.
- Foundry IQ portal experiences, query-time ACL features, and some toolbox capabilities can be preview even when core agentic retrieval APIs are generally available.
- Agent 365 live activation requires a qualifying license, tenant enablement, accepted terms, and Microsoft 365 or Entra administrator actions that cannot be automated without those privileges.
- OAuth identity passthrough requires same-tenant users with at least the Foundry Agent Consumer role; cross-tenant token exchange is not supported.
- The four Azure AI Search services are intentional security boundaries and create additional recurring cost.
- Resource creation incurs Azure charges until the demo environment is removed.
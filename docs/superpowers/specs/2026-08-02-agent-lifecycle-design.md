# Agent Lifecycle on Microsoft Foundry

## Purpose

Build a reproducible demonstration repository for the full lifecycle of a Microsoft Foundry Hosted Agent: build, evaluate, deploy, observe, and continuously evaluate production traffic. The repository must provision an isolated demo environment, deploy a working agent, enforce a pre-release quality gate, and activate an operational evaluation loop.

## Scope

The demo includes:

- A Python Hosted Agent built with Microsoft Agent Framework.
- The OpenAI-compatible Responses protocol, version 2.0.0.
- Azure Developer CLI configuration for infrastructure and agent deployment.
- Local development, tests, and VS Code Agent Inspector debugging.
- Seed smoke and regression evaluation datasets.
- Batch evaluation and a deployment quality gate.
- Application Insights tracing and Foundry monitoring.
- A continuous evaluation rule for deployed agent responses.
- GitHub Actions authentication through OpenID Connect.
- A private GitHub repository named `Agent-lifecycle-Azure-foundry`.

The demo does not include a business data source, external API, or Foundry Toolbox. Those integrations are extension points and are not required to prove the lifecycle.

## Agent Scenario

The deployed agent is a concise Microsoft Foundry operations guide. It answers questions about building, evaluating, deploying, and operating agents. Its narrow scope keeps the expected behavior deterministic enough for a meaningful lifecycle evaluation while remaining recognizable in a live demonstration.

## Architecture

The agent runs on the Microsoft Foundry Hosted Agent runtime. Microsoft Agent Framework supplies the agent abstraction, `FoundryChatClient`, and automatic OpenTelemetry instrumentation. The Foundry hosting package exposes the agent through the Responses protocol. The platform manages conversation history, streaming, runtime identity, and scale.

`azure.yaml` is the deployment source of truth. It defines a Foundry project service, a model deployment, and a hosted agent service. `azd provision` creates or updates the Azure resources. `azd deploy` packages and publishes a new agent version. The first model candidate is `gpt-5.4-mini`, subject to subscription, region, quota, and catalog validation before provisioning.

Application Insights receives server-side Hosted Agent telemetry. Sensitive prompt and response content is not enabled by default. Foundry's monitoring dashboard surfaces latency, token usage, run success, and evaluation scores.

## Repository Layout

```text
.
|-- .foundry/
|   |-- agent-metadata.yaml
|   |-- datasets/
|   |-- evaluators/
|   |-- results/
|   `-- suites/
|-- .github/
|   `-- workflows/
|       |-- ci.yml
|       `-- deploy-evaluate.yml
|-- .vscode/
|   |-- launch.json
|   `-- tasks.json
|-- docs/
|   |-- operations.md
|   `-- superpowers/
|       `-- specs/
|-- evals/
|   |-- data/
|   |   |-- regression.jsonl
|   |   `-- smoke.jsonl
|   `-- validate_dataset.py
|-- scripts/
|   |-- configure_continuous_evaluation.py
|   |-- verify_deployment.py
|   `-- verify_environment.ps1
|-- src/
|   `-- lifecycle_agent/
|       |-- __init__.py
|       |-- config.py
|       |-- main.py
|       `-- prompts/
|           `-- system.md
|-- tests/
|-- .env.example
|-- .gitignore
|-- AGENTS.md
|-- azure.yaml
|-- eval.yaml
|-- pyproject.toml
|-- README.md
`-- requirements.txt
```

## Build Flow

1. Install the pinned dependencies from `requirements.txt` into a virtual environment.
2. Load the Foundry project endpoint and model deployment name from environment variables.
3. Create the Agent Framework agent with `store` disabled because the Hosted Agent Responses runtime owns conversation history.
4. Start the Responses server on port 8088 for local development.
5. Use Ruff and Pytest for fast local validation.
6. Use the VS Code task and launch configuration for Agent Inspector and debugger attachment.

The implementation uses `DefaultAzureCredential`; it never accepts or stores an Azure API key.

## Evaluation Flow

The seed datasets use JSONL records with `query` and `expected_behavior`. The smoke suite is deliberately small and checks the highest-value behaviors before deployment. The regression suite provides broader lifecycle coverage and grows from reviewed production traces.

The initial evaluation dimensions are:

- Intent resolution.
- Task adherence.
- Response relevance.

`eval.yaml` defines the target agent, seed dataset, evaluators, maximum sample count, and passing threshold. CI runs the same recipe used locally. A failed threshold blocks the release workflow. Evaluation output is persisted as a workflow artifact; generated local results are ignored by Git unless explicitly curated.

## Deployment And CI/CD Flow

Pull requests run dependency installation, linting, unit tests, dataset validation, and configuration checks without modifying Azure resources.

A merge to `main` or a manual dispatch runs the deployment workflow:

1. Authenticate to Azure with GitHub OpenID Connect.
2. Install `azd` and the Foundry extensions.
3. Restore the named `azd` environment.
4. Run `azd provision` and `azd deploy` non-interactively.
5. Verify the Hosted Agent reaches an active state.
6. Invoke a representative smoke prompt.
7. Run the stored evaluation recipe and enforce its threshold.
8. Verify that the continuous evaluation rule is enabled.

The workflow identity receives only the roles required by provisioning, agent deployment, evaluation, and telemetry access. Repository variables hold non-secret identifiers. No long-lived client secret is used.

## Operate Flow

The first deployment connects Application Insights and enables server-side tracing. Operators use Foundry Monitor for latency, token usage, success rate, and evaluation trends. The continuous evaluation setup script creates an evaluation definition and an enabled response-completed rule filtered to the deployed agent, with a bounded hourly run count.

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
- The Hosted Agent deploys and reaches an active state.
- A remote smoke invocation returns a valid response.
- The initial batch evaluation completes and meets the configured threshold.
- Application Insights receives Hosted Agent telemetry.
- The continuous evaluation rule exists, is enabled, and targets the deployed agent.
- The private GitHub repository contains the verified implementation and workflows.

## Operational Constraints

- Azure and Foundry authentication remain user-owned interactive steps. Automation uses existing authenticated sessions or workload identity.
- The chosen model and region must be validated against the user's subscription before provisioning.
- Continuous evaluation and some `azd ai agent eval` features are preview capabilities and are not represented as generally available production guarantees.
- Resource creation incurs Azure charges until the demo environment is removed.
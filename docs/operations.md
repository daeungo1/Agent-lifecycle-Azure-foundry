# Operate: Continuous Evaluation and Agent 365

## Agent Tracing

Every hosted agent exports OpenTelemetry spans to Application Insights, and the Foundry
project carries an `AppInsights` connection so the portal can render them.

- Resources: `appi-<token>` (Application Insights) and `log-<token>` (Log Analytics),
  named from the Foundry account token so they stay aligned with the environment.
- Project connection: `appinsights-connection`, category `AppInsights`.
- Runtime wiring: `azure.yaml` passes `APPLICATIONINSIGHTS_CONNECTION_STRING` to each
  agent, and `configure_observability` enables the Azure Monitor exporter when it is set.
- Each agent sets `OTEL_SERVICE_NAME` to `<department>-agent`, so spans arrive with
  `cloud_RoleName` identifying the department. Without it every span is reported as
  `unknown_service` and the three agents cannot be told apart.

Confirm telemetry with:

```kusto
union dependencies, requests, traces
| where timestamp > ago(1h)
| summarize events = count(), lastSeen = max(timestamp) by itemType, cloud_RoleName
| order by events desc
```

### Why observability is provisioned by a hook, not by `azd provision`

The `microsoft.foundry` provider synthesises its own ARM template containing only the
Foundry account, project and model deployment. Resources declared in
`deploy/infra/main.bicep` are never sent to ARM — exporting the deployed template shows
none of them. `deploy/infra/modules/observability.bicep` is therefore deployed by
`lifecycle_ops.provisioning.observability` from the `postprovision` hook, the same way
knowledge bases, toolboxes and RBAC are. It runs first because the agents read the
connection string at deploy time.

The same limitation applies to the four Search services declared in `main.bicep`: they
exist only because an earlier deployment created them. Treat `main.bicep` as inert for
anything beyond the account, project and model deployment.

## Foundry Monitor Workflow

1. Open the Foundry project Monitor panel.
2. Filter traces by hosted agent name (`development-agent`, `human-resources-agent`, `marketing-agent`).
3. Review latency, failures, and evaluator outcomes per department.
4. Correlate incidents to exact rule id (`continuous-response-completed-<department>`).

## Continuous Evaluation Rules

- Evaluation source event: response completed.
- Enabled departments: development, human-resources, marketing.
- Deterministic rule ids:
  - `continuous-response-completed-development`
  - `continuous-response-completed-human-resources`
  - `continuous-response-completed-marketing`
- Deterministic eval names:
  - `continuous-eval-development`
  - `continuous-eval-human-resources`
  - `continuous-eval-marketing`
- Built-in evaluator baseline:
  - `intent_resolution`
  - `task_adherence`
  - `relevance`
- Hourly run cap is conservative and bounded to 20 or less.

The deployment gate and continuous evaluation serve different purposes:

- The deployment gate uses fixed versioned datasets and four evaluators: intent resolution,
  task adherence, relevance, and groundedness. It blocks promotion.
- Continuous evaluation samples deployed response traffic and uses the three lower-cost signal
  evaluators: intent resolution, task adherence, and relevance. It is non-blocking and bounded to
  20 runs per hour.
- The Operate stage registers or updates deterministic evaluation rules after the deployment gate
  succeeds. Foundry executes subsequent evaluations when response-completed events occur.

### Why tool-call accuracy is not in the gate

`ToolCallAccuracyEvaluator` requires a `tool_definitions` input. The
`azure_ai_target_completions` data source built by `azd ai agent eval run` maps only
`{{item.query}}` into the conversation and offers no evaluator data mapping, so the evaluator
errors on every sample. Adding `tool_definitions` to the dataset rows does not help, because the
field is never mapped to the evaluator. A permanently erroring criterion would block every
promotion for a reason unrelated to agent quality, so the criterion is omitted and recorded here.
Re-add `builtin.tool_call_accuracy` to `evals/eval.yaml` once the eval configuration supports
evaluator data mapping.

### Evaluator identifiers

Both the gate config and the continuous evaluation criteria address service evaluators as
`builtin.<name>`. The Foundry evals API rejects bare names with `EvaluatorNotFound`. The AI-assisted
evaluators also require a judge model, supplied as `options.eval_model` in `evals/eval.yaml`.

### Reading gate results

`azd ai agent eval run` writes progress text, not machine-readable JSON. Export the structured run
with `azd ai agent eval show <eval-id> --eval-run-id <run-id> --out-file <path>` and pass that file
to `python -m lifecycle_ops.evaluation.gate`. The export reports pass and fail counts per criterion
rather than scores, so the gate scores each criterion as its pass rate over evaluated samples and
counts errored samples as failures.

## Agent 365 Registry Verification

1. Verify `Agent365Observability` service principal exists.
2. Verify app role `Agent365.Observability.OtelWrite` exists.
3. Verify assignment exists for the hosted agent identity object id.
4. Default mode is read-only verification.
5. Optional `--grant` mode attempts assignment only when the operator has Graph directory rights.

Status contract:
- `verified`: prerequisites and assignment are confirmed.
- `prerequisite-skipped`: tenant/license/admin prerequisites are missing; keep App Insights runtime path.
- `failed`: malformed config, permission-denied after prerequisites were claimed, or assignment drift.

## Agent 365 Package Readiness

- Preferred runtime path: Microsoft OpenTelemetry Distro.
- Fallback compatibility path: Agent 365 extension packages.
- If package prerequisites cannot be resolved, mark readiness `prerequisite-skipped` and keep App Insights as runtime observability.
- Sensitive invocation input is suppressed by default.

## Trace To Regression Promotion

1. Export representative traces from production incidents.
2. Convert accepted traces into regression dataset entries.
3. Re-run regression evaluation before release promotion.
4. Promote only when no new regression failures are introduced.

## Access Reviews

- Review hosted agent identity role assignments at least monthly.
- Validate least-privilege access for data stores, tools, and observability sinks.
- Remove stale assignments during each review cycle.

## Version Rollback

1. Disable affected continuous evaluation rule if signal is noisy or broken.
2. Roll back agent/runtime deployment to last known good artifact.
3. Re-enable rule after confirming healthy traces and stable evaluator outcomes.

## Continuous Evaluation Limits

- Keep hourly execution limits conservative to avoid runaway spend.
- Increase only after sustained low-noise signal quality.
- Document limit changes in release notes and operations logs.

## Data Residency

- Ensure observability export and trace retention remain within approved residency boundaries.
- Validate residency whenever workspace, project region, or sink configuration changes.

## Teardown

1. Delete or disable continuous evaluation rules by deterministic ids.
2. Remove optional Agent 365 role assignment if no longer needed.
3. Keep audit evidence for deprovisioning and access review closure.

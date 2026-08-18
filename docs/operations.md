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

### Why observability is provisioned by a hook

`azure.yaml` now uses the built-in `bicep` provider, so `deploy/infra/main.bicep` is
deployed as written. The `microsoft.foundry` provider it replaced synthesised its own ARM
template containing only the Foundry account, project and model deployment: resources
declared in `main.bicep` — the four Search services, role assignments, everything — were
silently dropped, which is why exporting a deployment made under that provider shows none
of them.

`deploy/infra/modules/observability.bicep` is still deployed by
`lifecycle_ops.provisioning.observability` from the `postprovision` hook rather than from
`main.bicep`. The hook publishes `APPLICATIONINSIGHTS_CONNECTION_STRING` to the azd
environment, which `azure.yaml` then forwards to the agents at deploy time, and it keeps
working on environments that predate the provider switch. It runs before the knowledge
base and toolbox steps.

### Migrating an environment created under the foundry provider

The Foundry account in such an environment was named by that provider, and the Search
services were created before names carried a deterministic suffix. Neither matches what
`main.bicep` computes, so `azd provision --preview` reports the existing resources as
`Skip` and proposes `Create` for a differently named account and four suffixed Search
services. That is a migration, not an in-place update: running it leaves the old resources
in place and bills for both sets.

Before provisioning such an environment, decide whether to migrate to the new names and
decommission the old resources, or to keep the existing environment and deploy only agent
code with `azd deploy`.

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

## azd CLI Version And Extension Auth

The lifecycle is validated with `azd` 1.31.1, and `.github/workflows/deploy-evaluate.yml`
pins `Azure/setup-azd@v2` to that version so local and CI runs resolve the same command
surface.

`azd ai` extension commands acquire their token by shelling out to `azd auth token`, and the
extension abandons that probe after 10 seconds. On a slow network the probe exceeds the
budget and every extension command fails with `AzureDeveloperCLICredential: exit status 1`,
even though `azd auth login --check-status` succeeds and `azd provision` and `azd deploy`
work normally. This is latency, not a broken sign-in, so repeating `azd auth login` does not
help.

Diagnose it with `azd ai agent doctor`, which reports the real cause as
`Token acquisition timed out after 10s`. Confirm by timing the probe directly:

```powershell
Measure-Command { azd auth token --output json --scope "https://ai.azure.com/.default" }
```

`azd version` completing in well under a second while the token probe takes longer than ten
confirms token endpoint latency rather than a slow CLI. The deployed agents are unaffected
while the extension path is degraded; verify them with a direct REST call to the project
responses endpoint.

## Continuous Evaluation And Hosted Agents

Continuous evaluation rules register successfully and fire on every agent response,
but each run fails immediately with `total = 0`:

```
UserError: Evaluation failed with AOAI error: Error code: 403 -
{'error': {'code': 'session_not_accessible', 'message': 'Session is not accessible.'}}
inner_error: PermissionDenied
```

This is a platform limitation, not a misconfiguration. A `ResponseCompleted` rule
builds its item with `response_retrieval`, which reads the response back through the
project. Hosted agents cannot produce responses there. Calling the documented
project path returns:

```
400 bad_request: Hosted agents can only be called through the agent endpoint:
https://<account>.services.ai.azure.com/api/projects/<project>/agents/<agentName>/endpoint/protocols/openai/responses
```

So a hosted agent response only ever exists inside an agent session owned by the
caller, and the evaluation service cannot read that session.

Ruled out by testing, so do not spend time on them again:

- Project managed identity RBAC. `Foundry User` at project scope, `Foundry User` at
  account scope, and `Log Analytics Reader` on both Application Insights and its
  workspace are all assigned. The failure is unchanged after propagation.
- Stale environment values. The failure reproduces against a freshly refreshed
  environment pointing at the live account.

The deployment gate is unaffected because it runs one-off evaluations that generate
their own responses. Treat the gate as the enforcing control and the continuous
rules as registered but not yet producing results. Re-test after the hosted agent
and evaluation services converge; the rules need no change.

## Teardown

1. Delete or disable continuous evaluation rules by deterministic ids.
2. Remove optional Agent 365 role assignment if no longer needed.
3. Keep audit evidence for deprovisioning and access review closure.

# Operate: Continuous Evaluation and Agent 365

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

- The deployment gate uses fixed versioned datasets and five evaluators: intent resolution,
  task adherence, relevance, tool-call accuracy, and groundedness. It blocks promotion.
- Continuous evaluation samples deployed response traffic and uses the three lower-cost signal
  evaluators: intent resolution, task adherence, and relevance. It is non-blocking and bounded to
  20 runs per hour.
- The postdeploy command registers or updates deterministic evaluation rules. Foundry executes
  subsequent evaluations when response-completed events occur.

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

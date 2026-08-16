# AGENTS

## Scope

This repository contains the lifecycle implementation for enterprise Microsoft Foundry Hosted Agents.

## Guardrails

- Do not commit secrets or tokens.
- Use managed identity and `DefaultAzureCredential` for Azure access.
- Keep department isolation rules intact.
- Preserve Build -> Evaluate -> Operate lifecycle order in changes.
- Keep deploy hooks thin; lifecycle logic belongs in `src/lifecycle_ops`.
- Keep indexed content under `knowledge/` and configuration outside it.
- Use `departments.yaml` and `lifecycle_ops.naming` for department-derived values.
- Verify Build -> Evaluate -> Operate ordering after workflow changes.
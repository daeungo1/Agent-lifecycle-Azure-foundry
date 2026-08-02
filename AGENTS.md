# AGENTS

## Scope

This repository contains the lifecycle implementation for enterprise Microsoft Foundry Hosted Agents.

## Guardrails

- Do not commit secrets or tokens.
- Use managed identity and `DefaultAzureCredential` for Azure access.
- Keep department isolation rules intact.
- Preserve Build -> Evaluate -> Operate lifecycle order in changes.
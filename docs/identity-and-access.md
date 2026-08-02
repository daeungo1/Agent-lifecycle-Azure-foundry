# Identity and Access: Toolboxes, Agent Identity RBAC, and OBO Extension

## Current quickstart path (synthetic Foundry IQ)

The quickstart knowledge endpoints (`KB_MCP_ENDPOINT_*`) are deployed for synthetic data and must use Agentic Identity:

- RemoteTool connections are created with `--auth-type agentic-identity`.
- Audience is always `https://search.azure.com`.
- API keys are not used.

Because these are synthetic boundaries with fixed authorization, this path does not require user token passthrough.

## Toolbox authorization boundaries

Each department toolbox is intentionally limited to two connections:

- shared boundary connection (`kb-shared-remote-tool`)
- department-private connection (`kb-<department>-remote-tool`)

No toolbox includes another department's private connection.

## Agent identity RBAC

`scripts/set_agent_rbac.py` enforces least privilege by:

- resolving each hosted agent `instance_identity.principal_id` with `AIProjectClient`
- assigning `Search Index Data Reader` only on:
  - shared search resource
  - the agent's own department search resource
- verifying no cross-department `Search Index Data Reader` assignments exist among known boundaries (`shared`, `development`, `human-resources`, `marketing`)
- writing a machine-readable JSON report and failing when forbidden boundary assignments are found

The script does not remove unrelated assignments automatically.

## OBO extension pattern (future ACL-aware MCP)

Use OBO only for future ACL-aware MCP sources where caller identity must flow to downstream data services.

Required conditions:

- same Microsoft Entra tenant for client app, Foundry project, and downstream API
- Foundry app registration granted **Foundry Agent Consumer**
- delegated permission includes `offline_access`
- custom API audience (`api://<app-id-or-uri>`) configured for token exchange

Security requirements:

- never pass raw user access tokens to agent instructions, agent memory, or tool payload text
- use structured OAuth2 token exchange through trusted platform identity plumbing
- keep token handling in middleware/service infrastructure, not prompt content

Reference template: `docs/obo-toolbox-oauth2.template.yaml`

This template is intentionally disabled for the synthetic Foundry IQ quickstart and is not referenced by `azure.yaml`.

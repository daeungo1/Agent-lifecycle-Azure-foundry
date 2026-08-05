# Architecture SVG Design

## Purpose

Replace the README lifecycle PNG with a self-contained SVG and add a second SVG that explains the deployed Azure resources from a Cloud Solution Architect perspective.

## Approaches Considered

1. Keep one diagram and convert it to SVG. This preserves the current layout but does not provide the requested Azure resource view.
2. Use two purpose-specific SVGs. One explains the Build, Evaluate, and Operate workflow; the other maps Azure control plane, data plane, identity, observability, and optional production hardening. This is the selected approach.
3. Combine workflow and Azure resources into one large SVG. This reduces the asset count but makes lifecycle gates and resource ownership harder to scan.

## Lifecycle Workflow SVG

The workflow diagram uses a left-to-right lifecycle with four grouped stages:

- Build: GitHub Actions with OIDC, tests, Bicep validation, and direct code packaging.
- Provision and deploy: Foundry project and model, three department Hosted Agents, department toolboxes, and four Foundry IQ knowledge boundaries.
- Evaluate: smoke invocation, quality and security evaluators, and a fail-closed release gate.
- Operate: Application Insights, continuous evaluation, Agent 365 governance, and a feedback path that returns curated failures to the Build stage.

The three department branches remain visible without duplicating every specialist. Identity and RBAC appear as a cross-cutting enforcement rail.

## CSA Azure Resource SVG

The resource diagram distinguishes three states without relying only on color:

- Solid lines and filled containers: resources created by Bicep or `azd provision`.
- Dashed lines: resources and bindings configured after provisioning by repository scripts or `azd deploy`.
- Dotted containers: optional production-hardening targets supported by the Foundry network parameters but not enabled in the current baseline.

The current-state resource hierarchy is:

- Azure subscription and `rg-agent-lifecycle-demo`.
- Microsoft Foundry AIServices account.
- Foundry project and `gpt-5.4-mini` deployment.
- Three immutable Hosted Agent deployments using direct code deployment.
- Four Basic Azure AI Search services with local authentication disabled.
- Four Foundry IQ knowledge bases and three department toolboxes configured after provisioning.
- Entra ID and Azure RBAC assignments for provisioning and department-scoped retrieval.
- Application Insights and Agent 365 as operate-plane integrations.

The target-state boundary shows private endpoint, private DNS, and managed or bring-your-own network egress as optional hardening, clearly separated from the current public-endpoint baseline.

## Visual System

- White canvas with dark navy text for GitHub light and dark theme readability.
- Blue for lifecycle/control plane, teal for agent compute, amber for evaluation, violet for knowledge, and green for operations.
- Rounded rectangles use at most an 8 px radius.
- Labels remain short; explanatory detail stays in legends and README prose.
- Every SVG includes `title`, `desc`, stable `viewBox`, and accessible role metadata.

## README Integration

The lifecycle SVG replaces the existing PNG directly below the introduction. The editable Excalidraw link remains available as the historical source. A new `Azure resource architecture` section embeds the CSA SVG and explains the current versus target-state line conventions.

## Validation

- Parse each SVG as XML.
- Verify required labels, groups, and line-style legends.
- Render both assets in a browser at desktop and mobile widths.
- Confirm no blank canvas, clipped nodes, overlapping labels, or broken README paths.
- Run repository tests, Ruff, Bicep compilation, and README/diagram contract tests before commit and push.
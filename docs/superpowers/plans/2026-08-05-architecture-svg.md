# Architecture SVG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the README lifecycle PNG with an accessible SVG and add a second CSA-focused SVG that maps the current Azure deployment and optional production hardening.

**Architecture:** Keep two self-contained SVG assets under `docs/architecture/`. Extend the existing documentation contract tests to parse SVG XML, require stable groups and labels, and verify README embeds. Validate final visual output in Chromium at desktop and mobile widths.

**Tech Stack:** SVG 1.1/XML, Markdown, Python 3.13, pytest, Playwright/Chromium for visual verification.

## Global Constraints

- Preserve Build -> Evaluate -> Operate lifecycle order.
- Keep department isolation rules intact.
- Current resources use solid styling, post-provision bindings use dashed styling, and optional production hardening uses dotted styling.
- Use ASCII text in SVG source and include `title`, `desc`, `role="img"`, and a stable `viewBox`.
- Do not add secrets, tokens, remote fonts, JavaScript, or external SVG dependencies.

---

### Task 1: SVG Documentation Contract

**Files:**
- Modify: `tests/test_documentation.py`
- Test: `tests/test_documentation.py`

**Interfaces:**
- Consumes: repository root and `docs/architecture/` asset paths.
- Produces: `_load_svg(name: str) -> ElementTree.Element` and contract tests for both SVG assets and README embeds.

- [ ] **Step 1: Write failing SVG and README tests**

Add XML parsing and stable ID/label assertions:

```python
import xml.etree.ElementTree as ET


def _architecture_svg_path(name: str) -> Path:
    return _repo_root().joinpath("docs", "architecture", name)


def _load_svg(name: str) -> ET.Element:
    path = _architecture_svg_path(name)
    assert path.exists(), f"Missing SVG: {path}"
    return ET.parse(path).getroot()


def test_lifecycle_workflow_svg_contract() -> None:
    root = _load_svg("agent-lifecycle-workflow.svg")
    source = ET.tostring(root, encoding="unicode")
    assert root.attrib["viewBox"] == "0 0 1440 900"
    for label in ["Build", "Provision and deploy", "Evaluate", "Operate", "Feedback loop"]:
        assert label in source


def test_azure_resource_svg_contract() -> None:
    root = _load_svg("azure-resource-architecture.svg")
    source = ET.tostring(root, encoding="unicode")
    assert root.attrib["viewBox"] == "0 0 1440 1000"
    for label in ["Azure subscription", "Microsoft Foundry", "gpt-5.4-mini", "Azure AI Search", "Private endpoint"]:
        assert label in source
```

Update the README contract to require both SVG embeds:

```python
assert "(docs/architecture/agent-lifecycle-workflow.svg)" in content
assert "(docs/architecture/azure-resource-architecture.svg)" in content
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```powershell
.\.venv\python.exe -m pytest tests/test_documentation.py -q
```

Expected: FAIL because both SVG files and README embeds are missing.

- [ ] **Step 3: Keep the red test and implementation in one documentation commit**

Do not leave `main` red between commits. Complete Tasks 2 and 3 before committing the contract.

### Task 2: Lifecycle Workflow SVG

**Files:**
- Create: `docs/architecture/agent-lifecycle-workflow.svg`
- Modify: `README.md`
- Test: `tests/test_documentation.py`

**Interfaces:**
- Consumes: lifecycle ordering from `.github/workflows/deploy-evaluate.yml` and department topology from `departments.yaml`.
- Produces: a self-contained `0 0 1440 900` workflow SVG embedded near the README introduction.

- [ ] **Step 1: Create the lifecycle SVG**

Use these stable semantic groups and labels:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 900" role="img" aria-labelledby="title desc">
  <title id="title">Enterprise Agent Lifecycle</title>
  <desc id="desc">Build, provision, evaluate, and operate workflow for three department agents.</desc>
  <g id="build-stage" aria-label="GitHub OIDC build and validation" />
  <g id="provision-stage" aria-label="Azure provision and direct code deployment" />
  <g id="department-agents" aria-label="Three department hosted agents" />
  <g id="knowledge-boundaries" aria-label="Shared and department knowledge boundaries" />
  <g id="evaluate-stage" aria-label="Quality and security release gate" />
  <g id="operate-stage" aria-label="Observability continuous evaluation and governance" />
  <g id="identity-rail" aria-label="Entra ID managed identity and Azure RBAC" />
  <g id="feedback-loop" aria-label="Curated production trace feedback" />
</svg>
```

The stage order is GitHub OIDC -> tests and Bicep -> provision and direct code deploy -> department agents and toolboxes -> quality and security gate -> observability and governance -> curated trace feedback.

- [ ] **Step 2: Replace the README PNG embed**

Use:

```markdown
![Enterprise agent lifecycle workflow](docs/architecture/agent-lifecycle-workflow.svg)
```

Keep the existing editable Excalidraw source link as a historical editable artifact.

- [ ] **Step 3: Run the lifecycle contract**

Run:

```powershell
.\.venv\python.exe -m pytest tests/test_documentation.py -q
```

Expected: lifecycle SVG assertions pass; CSA SVG assertions still fail.

### Task 3: CSA Azure Resource SVG and Final Validation

**Files:**
- Create: `docs/architecture/azure-resource-architecture.svg`
- Modify: `README.md`
- Test: `tests/test_documentation.py`

**Interfaces:**
- Consumes: `infra/main.bicep`, `infra/modules/resources.bicep`, `infra/modules/search.bicep`, `azure.yaml`, and post-provision scripts.
- Produces: a self-contained `0 0 1440 1000` CSA resource SVG and README resource architecture section.

- [ ] **Step 1: Create the CSA resource SVG**

Use these stable semantic groups:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 1000" role="img" aria-labelledby="title desc">
  <title id="title">Azure Resource Architecture</title>
  <desc id="desc">Current Azure resources, post-provision bindings, and optional production hardening.</desc>
  <g id="delivery-plane" aria-label="GitHub Actions OIDC and Azure deployment" />
  <g id="identity-plane" aria-label="Microsoft Entra ID and Azure RBAC" />
  <g id="azure-subscription" aria-label="Azure subscription boundary" />
  <g id="resource-group" aria-label="rg-agent-lifecycle-demo" />
  <g id="foundry-account" aria-label="Microsoft Foundry AIServices account" />
  <g id="foundry-project" aria-label="Foundry project and model deployment" />
  <g id="hosted-agents" aria-label="Three direct code hosted agents" />
  <g id="search-boundaries" aria-label="Four isolated Azure AI Search services" />
  <g id="operate-integrations" aria-label="Application Insights and Agent 365" />
  <g id="target-hardening" aria-label="Optional private networking hardening" />
  <g id="legend" aria-label="Current post-provision and target state legend" />
</svg>
```

Show current Bicep resources with solid lines, toolbox/knowledge/RBAC bindings with dashed lines, and VNet/private endpoint/private DNS targets with dotted lines.

- [ ] **Step 2: Add the README resource architecture section**

Add directly after `Architecture focus`:

```markdown
## Azure resource architecture

![Azure resource architecture](docs/architecture/azure-resource-architecture.svg)

Solid paths are provisioned by Bicep or `azd`; dashed paths are post-provision bindings; dotted boundaries are optional production hardening and are not enabled in the current baseline.
```

- [ ] **Step 3: Run executable validation**

Run:

```powershell
.\.venv\python.exe -m pytest tests/test_documentation.py -q
.\.venv\python.exe -m pytest -q
.\.venv\python.exe -m ruff check .
az bicep build --file infra/main.bicep --stdout | Out-Null
az bicep build-params --file infra/main.bicepparam --stdout | Out-Null
```

Expected: all tests pass, Ruff reports `All checks passed!`, and both Bicep commands exit 0.

- [ ] **Step 4: Render desktop and mobile screenshots**

Open the README or a minimal local HTML wrapper in Chromium at 1440 x 1100 and 390 x 844. Verify both SVG canvases are nonblank, labels remain inside nodes, no connectors cross labels, and no content clips the `viewBox`.

- [ ] **Step 5: Commit and push**

```bash
git add README.md docs/architecture/*.svg docs/superpowers/specs/2026-08-05-architecture-svg-design.md docs/superpowers/plans/2026-08-05-architecture-svg.md tests/test_documentation.py
git commit -m "docs: add lifecycle and Azure resource SVGs"
git push origin main
```
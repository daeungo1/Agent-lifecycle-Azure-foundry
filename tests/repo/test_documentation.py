from __future__ import annotations

import importlib.util
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageStat


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _architecture_source_path() -> Path:
    return _repo_root().joinpath("docs", "architecture", "enterprise-agent-lifecycle.excalidraw")


def _architecture_png_path() -> Path:
    return _repo_root().joinpath("docs", "architecture", "enterprise-agent-lifecycle.png")


def _architecture_svg_path(name: str) -> Path:
    return _repo_root().joinpath("docs", "architecture", name)


def _readme_path() -> Path:
    return _repo_root().joinpath("README.md")


def _load_architecture() -> dict:
    source = _architecture_source_path()
    assert source.exists(), f"Missing architecture source: {source}"
    return json.loads(source.read_text(encoding="utf-8"))


def _load_svg(name: str) -> ET.Element:
    path = _architecture_svg_path(name)
    assert path.exists(), f"Missing SVG: {path}"
    return ET.parse(path).getroot()


def _svg_group_ids(root: ET.Element) -> set[str]:
    return {
        element.attrib["id"]
        for element in root.iter("{http://www.w3.org/2000/svg}g")
        if "id" in element.attrib
    }


def _assert_safe_self_contained_svg(root: ET.Element, source: str) -> None:
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.attrib.get("role") == "img"
    assert root.attrib.get("aria-labelledby") == "title desc"
    assert root.find("{http://www.w3.org/2000/svg}title") is not None
    assert root.find("{http://www.w3.org/2000/svg}desc") is not None
    assert "<script" not in source.lower()
    assert all(ord(char) < 128 for char in source), "SVG source must remain ASCII"

    for element in root.iter():
        for attribute, value in element.attrib.items():
            if attribute.endswith("href"):
                assert not value.startswith(("http://", "https://", "data:"))


def _elements_by_id(data: dict) -> dict[str, dict]:
    elements = data.get("elements")
    if not isinstance(elements, list):
        return {}
    by_id: dict[str, dict] = {}
    for element in elements:
        element_id = element.get("id")
        if isinstance(element_id, str):
            by_id[element_id] = element
    return by_id


def _element_points(element: dict) -> list[tuple[float, float]]:
    points = element.get("points") or []
    base_x = float(element.get("x", 0))
    base_y = float(element.get("y", 0))
    return [(base_x + float(px), base_y + float(py)) for px, py in points]


def _segment_intersects_rect(
    a: tuple[float, float],
    b: tuple[float, float],
    rect: tuple[float, float, float, float],
) -> bool:
    x0, y0, x1, y1 = rect
    steps = 40
    for idx in range(1, steps):
        t = idx / steps
        x = a[0] + (b[0] - a[0]) * t
        y = a[1] + (b[1] - a[1]) * t
        if x0 < x < x1 and y0 < y < y1:
            return True
    return False


def _rect_bounds(element: dict) -> tuple[float, float, float, float]:
    x = float(element.get("x", 0))
    y = float(element.get("y", 0))
    width = float(element.get("width", 0))
    height = float(element.get("height", 0))
    return (x, y, x + width, y + height)


def _rectangles_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    return (a[0] < b[2]) and (a[2] > b[0]) and (a[1] < b[3]) and (a[3] > b[1])


def test_architecture_source_contract() -> None:
    data = _load_architecture()

    assert data.get("type") == "excalidraw"
    assert data.get("version") == 2

    elements = data.get("elements")
    assert isinstance(elements, list)
    assert elements, "Diagram must include elements"

    ids = [element.get("id") for element in elements]
    assert all(isinstance(item, str) and item for item in ids)
    assert len(ids) == len(set(ids)), "Element IDs must be unique"

    rectangles = [el for el in elements if el.get("type") == "rectangle"]
    assert 1 <= len(rectangles) < 20, "Use fewer than 20 high-level nodes"

    for element in elements:
        text = element.get("text")
        if isinstance(text, str) and text:
            assert element.get("fontFamily") == 5, "All diagram text must use Excalifont"
            assert all(ord(ch) < 128 for ch in text), "Diagram text must be English/ASCII"
        assert element.get("roughness") == 0

    curved_arrows = [
        el
        for el in elements
        if (
            el.get("type") == "arrow"
            and isinstance(el.get("points"), list)
            and len(el["points"]) >= 3
        )
    ]
    assert curved_arrows, "Expected smooth routed arrows with 3+ points"
    for arrow in curved_arrows:
        assert arrow.get("roundness", {}).get("type") == 2


def test_architecture_layout_contract() -> None:
    data = _load_architecture()
    elements = data["elements"]
    rectangles = [el for el in elements if el.get("type") == "rectangle"]
    bounds = [_rect_bounds(el) for el in rectangles]

    for i, left in enumerate(bounds):
        for right in bounds[i + 1 :]:
            assert not _rectangles_overlap(left, right), "Boxes must not overlap"

    for element in elements:
        if element.get("type") != "arrow":
            continue
        points = _element_points(element)
        if len(points) < 2:
            continue

        for start, end in zip(points[:-1], points[1:]):
            segment_len = math.dist(start, end)
            if segment_len < 2:
                continue
            for rect in bounds:
                assert not _segment_intersects_rect(start, end, rect), (
                    "Arrow route crosses a box interior; reroute through free space"
                )


def test_architecture_text_contract() -> None:
    data = _load_architecture()
    by_id = _elements_by_id(data)
    elements = data["elements"]
    text_elements = [element for element in elements if element.get("type") == "text"]
    assert text_elements, "Diagram must include text elements"

    for element in text_elements:
        text = element.get("text")
        if not isinstance(text, str):
            continue
        assert "\\n" not in text, "Use real newline escapes (\\n), not literal backslash-n"
        font_size = element.get("fontSize")
        assert isinstance(font_size, int)
        assert font_size >= 16, "All diagram text must be at least 16px"

    title = by_id.get("t-title")
    assert isinstance(title, dict), "Diagram title text is required"
    assert title.get("text") == "Enterprise Agent Lifecycle: Build -> Evaluate -> Operate"
    assert int(title.get("fontSize", 0)) >= 24


def test_architecture_text_within_boxes_contract() -> None:
    data = _load_architecture()
    by_id = _elements_by_id(data)

    text_to_rect = {
        "t-dev-agent": "r-dev-agent",
        "t-hr-agent": "r-hr-agent",
        "t-mkt-agent": "r-mkt-agent",
        "t-dev-toolbox": "r-dev-toolbox",
        "t-hr-toolbox": "r-hr-toolbox",
        "t-mkt-toolbox": "r-mkt-toolbox",
        "t-kb-shared": "r-kb-shared",
        "t-kb-dev": "r-kb-dev",
        "t-kb-hr": "r-kb-hr",
        "t-kb-mkt": "r-kb-mkt",
        "t-evaluate": "r-evaluate",
        "t-operate": "r-operate",
    }

    for text_id, rect_id in text_to_rect.items():
        text_el = by_id[text_id]
        rect_el = by_id[rect_id]

        tx = float(text_el["x"])
        ty = float(text_el["y"])
        tw = float(text_el["width"])
        th = float(text_el["height"])

        rx = float(rect_el["x"])
        ry = float(rect_el["y"])
        rw = float(rect_el["width"])
        rh = float(rect_el["height"])

        assert tx >= rx + 20, f"{text_id} must keep >=20px left padding"
        assert ty >= ry + 20, f"{text_id} must keep >=20px top padding"
        assert tx + tw <= rx + rw - 20, f"{text_id} must keep >=20px right padding"
        assert ty + th <= ry + rh - 20, f"{text_id} must keep >=20px bottom padding"


def test_renderer_multiline_layout_contract() -> None:
    repo_root = _repo_root()
    script_path = repo_root.joinpath("docs", "tools", "render_excalidraw.py")
    assert script_path.exists(), f"Missing renderer script: {script_path}"

    spec = importlib.util.spec_from_file_location("render_excalidraw", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert hasattr(module, "_layout_multiline_text"), "Renderer must expose multiline layout helper"

    font = module._load_font(18)
    lines, starts, total_height = module._layout_multiline_text(
        draw=None,
        text="Line A\nLine B\nLine C",
        font=font,
        box_x=100.0,
        box_y=200.0,
        box_w=240.0,
        box_h=140.0,
        spacing=4,
    )

    assert lines == ["Line A", "Line B", "Line C"]
    assert len(starts) == 3
    assert starts[0][0] >= 100.0
    assert starts[1][0] >= 100.0
    assert starts[2][0] >= 100.0
    assert starts[0][0] <= 340.0
    assert starts[1][0] <= 340.0
    assert starts[2][0] <= 340.0
    assert total_height <= 140.0


def test_architecture_png_contract() -> None:
    png_path = _architecture_png_path()
    assert png_path.exists(), f"Missing rendered PNG: {png_path}"
    assert png_path.stat().st_size > 0

    with Image.open(png_path) as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        assert width >= 1850
        assert height >= 950

        alpha = rgba.getchannel("A")
        alpha_extrema = alpha.getextrema()
        assert alpha_extrema[1] > 0, "Image cannot be fully transparent"

        rgb = rgba.convert("RGB")
        stat = ImageStat.Stat(rgb)
        variance = sum(stat.var) / len(stat.var)
        assert variance > 50.0, "Image appears blank or almost uniform"

        non_white = 0
        total = width * height
        for r, g, b in rgb.get_flattened_data():
            if (r, g, b) != (255, 255, 255):
                non_white += 1
        assert non_white > max(5000, total // 200), "Image cannot be all-white"


def test_lifecycle_workflow_svg_contract() -> None:
    root = _load_svg("agent-lifecycle-workflow.svg")
    source = ET.tostring(root, encoding="unicode")
    _assert_safe_self_contained_svg(root, source)

    assert root.attrib.get("viewBox") == "0 0 1440 900"
    assert {
        "build-stage",
        "provision-stage",
        "department-agents",
        "knowledge-boundaries",
        "evaluate-stage",
        "operate-stage",
        "identity-rail",
        "feedback-loop",
    } <= _svg_group_ids(root)

    for label in [
        "Build",
        "Provision and deploy",
        "Evaluate",
        "Operate",
        "Development",
        "Human Resources",
        "Marketing",
        "Foundry IQ",
        "Feedback loop",
    ]:
        assert label in source
    assert "Ruff + 117 tests" not in source


def test_azure_resource_svg_contract() -> None:
    root = _load_svg("azure-resource-architecture.svg")
    source = ET.tostring(root, encoding="unicode")
    _assert_safe_self_contained_svg(root, source)

    assert root.attrib.get("viewBox") == "0 0 1440 1000"
    assert {
        "delivery-plane",
        "identity-plane",
        "azure-subscription",
        "resource-group",
        "foundry-account",
        "foundry-project",
        "hosted-agents",
        "search-boundaries",
        "operate-integrations",
        "target-hardening",
        "legend",
        "department-knowledge-bindings",
    } <= _svg_group_ids(root)

    for label in [
        "Azure subscription",
        "rg-agent-lifecycle-demo",
        "Microsoft Foundry",
        "gpt-5.4-mini",
        "Hosted Agents",
        "Azure AI Search",
        "Microsoft Entra ID",
        "Application Insights",
        "Private endpoint",
        "Current deployment",
        "Post-provision binding",
        "Optional hardening target",
    ]:
        assert label in source
    for access_rule in ["Shared + Development", "Shared + HR", "Shared + Marketing"]:
        assert access_rule in source
    assert "Shared Foundry IQ knowledge base" not in source
    assert source.count('class="post"') >= 6
    assert "No resource provisioning is implied" in source
    assert "Verified or prerequisite-skipped" in source


def test_readme_architecture_and_commands_contract() -> None:
    readme = _readme_path()
    assert readme.exists(), f"Missing README: {readme}"

    content = readme.read_text(encoding="utf-8")
    assert content.startswith("# ")
    image_embed = (
        "![Enterprise agent lifecycle workflow]"
        "(docs/architecture/agent-lifecycle-workflow.svg)"
    )
    resource_embed = (
        "![Azure resource architecture]"
        "(docs/architecture/azure-resource-architecture.svg)"
    )
    source_link = (
        "[Legacy Excalidraw sketch]"
        "(docs/architecture/enterprise-agent-lifecycle.excalidraw)"
    )
    assert (
        image_embed in content
    )
    assert resource_embed in content
    assert source_link in content
    lifecycle_link = (
        "[Open full-size lifecycle SVG]"
        "(docs/architecture/agent-lifecycle-workflow.svg)"
    )
    resource_link = (
        "[Open full-size Azure resource SVG]"
        "(docs/architecture/azure-resource-architecture.svg)"
    )
    assert lifecycle_link in content
    assert resource_link in content
    assert "```excalidraw" not in content

    for phrase in [
        "Build",
        "Evaluate",
        "Operate",
        "department",
        "coordinator",
        "specialist",
        "Foundry IQ",
        "Agent365",
        "Entra",
        "RBAC",
        "OBO",
        "Azure cost",
    ]:
        assert phrase in content

    expected_commands = [
        "pip install -r requirements-dev.txt",
        "python -m venv .venv",
        "python agent.py",
        "azd provision --no-prompt",
        "azd deploy --no-prompt",
        "azd ai agent eval run --config evals/eval.yaml --no-prompt --output json",
        "python -m lifecycle_ops.evaluation.gate --config evals/eval.yaml",
        "python -m lifecycle_ops.operations.agent365.readiness",
        "python -m lifecycle_ops.operations.agent365.registry",
        "azd down --purge --force --no-prompt",
    ]
    for command in expected_commands:
        assert command in content


def test_original_design_matches_current_repository_layout_and_flow() -> None:
    design = _repo_root().joinpath(
        "docs",
        "superpowers",
        "specs",
        "2026-08-02-agent-lifecycle-design.md",
    ).read_text(encoding="utf-8")

    assert "|-- deploy/" in design
    assert "|   |-- hooks/" in design
    assert "|   `-- toolboxes/" in design
    assert "|   |-- lifecycle_agent/" in design
    assert "|   `-- lifecycle_ops/" in design
    assert "|-- .foundry/" not in design
    assert "|-- .vscode/" not in design
    assert "|-- scripts/" not in design

    deployment = design.split("## Deployment And CI/CD Flow", 1)[1].split(
        "## Operate Flow",
        1,
    )[0]
    provision = deployment.index("Run `azd provision`")
    postprovision = deployment.index("The `postprovision` hook")
    deploy = deployment.index("Run `azd deploy`")
    postdeploy = deployment.index("The `postdeploy` hook")
    evaluate = deployment.index("Run the deployment gate evaluation")
    assert provision < postprovision < deploy < postdeploy < evaluate


def test_readme_does_not_duplicate_azd_hook_operations() -> None:
    content = _readme_path().read_text(encoding="utf-8")

    for module in (
        "lifecycle_ops.provisioning.knowledge_bases",
        "lifecycle_ops.provisioning.toolboxes",
        "lifecycle_ops.provisioning.rbac",
        "lifecycle_ops.provisioning.continuous_eval",
    ):
        assert f"python -m {module}" not in content

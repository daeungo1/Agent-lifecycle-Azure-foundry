from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageStat


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _architecture_source_path() -> Path:
    return _repo_root().joinpath("docs", "architecture", "enterprise-agent-lifecycle.excalidraw")


def _architecture_png_path() -> Path:
    return _repo_root().joinpath("docs", "architecture", "enterprise-agent-lifecycle.png")


def _readme_path() -> Path:
    return _repo_root().joinpath("README.md")


def _load_architecture() -> dict:
    source = _architecture_source_path()
    assert source.exists(), f"Missing architecture source: {source}"
    return json.loads(source.read_text(encoding="utf-8"))


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


def test_architecture_png_contract() -> None:
    png_path = _architecture_png_path()
    assert png_path.exists(), f"Missing rendered PNG: {png_path}"
    assert png_path.stat().st_size > 0

    with Image.open(png_path) as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        assert width >= 1400
        assert height >= 800

        alpha = rgba.getchannel("A")
        alpha_extrema = alpha.getextrema()
        assert alpha_extrema[1] > 0, "Image cannot be fully transparent"

        rgb = rgba.convert("RGB")
        stat = ImageStat.Stat(rgb)
        variance = sum(stat.var) / len(stat.var)
        assert variance > 50.0, "Image appears blank or almost uniform"

        non_white = 0
        total = width * height
        for r, g, b in rgb.getdata():
            if (r, g, b) != (255, 255, 255):
                non_white += 1
        assert non_white > max(5000, total // 200), "Image cannot be all-white"


def test_readme_architecture_and_commands_contract() -> None:
    readme = _readme_path()
    assert readme.exists(), f"Missing README: {readme}"

    content = readme.read_text(encoding="utf-8")
    assert content.startswith("# ")
    image_embed = (
        "![Enterprise agent lifecycle architecture]"
        "(docs/architecture/enterprise-agent-lifecycle.png)"
    )
    source_link = (
        "[Edit Excalidraw source]"
        "(docs/architecture/enterprise-agent-lifecycle.excalidraw)"
    )
    assert (
        image_embed in content
    )
    assert source_link in content
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
        "pip install -r requirements.txt",
        "python -m venv .venv",
        "python services/agents/development/main.py",
        "python services/agents/human-resources/main.py",
        "python services/agents/marketing/main.py",
        "azd provision --no-prompt",
        "python scripts/provision_knowledge_bases.py",
        "pwsh -File scripts/configure_toolboxes.ps1",
        "azd deploy --no-prompt",
        "python scripts/set_agent_rbac.py",
        "azd ai agent eval run --config eval.yaml --no-prompt --output json",
        "python scripts/validate_eval_results.py --config eval.yaml",
        "python scripts/configure_continuous_evaluation.py",
        "python scripts/agent365/configure_observability.py",
        "python scripts/agent365/verify_registry.py --prerequisites-claimed",
        "azd down --purge --force --no-prompt",
    ]
    for command in expected_commands:
        assert command in content

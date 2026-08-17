from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SVG_NS = "{http://www.w3.org/2000/svg}"

# Hangul advances roughly one em; Latin is much narrower. The diagrams mix both, so a
# single ratio would either miss overflow or raise false alarms.
LATIN_RATIO = 0.58
HANGUL_RATIO = 1.0
SPACE_RATIO = 0.30

DIAGRAMS = (
    "lifecycle-stages.svg",
    "department-scenario.svg",
    "azure-resources.svg",
    "enterprise-detailed-architecture.svg",
)


def _architecture_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "architecture"


def _text_width(value: str, font_size: float) -> float:
    width = 0.0
    for char in value:
        if char == " ":
            width += font_size * SPACE_RATIO
        elif "\uac00" <= char <= "\ud7a3":
            width += font_size * HANGUL_RATIO
        else:
            width += font_size * LATIN_RATIO
    return width


def _class_font_sizes(source: str) -> dict[str, float]:
    sizes: dict[str, float] = {}
    for match in re.finditer(r"\.([a-zA-Z0-9_-]+)\s*\{([^}]*)\}", source):
        font = re.search(r"font:\s*[^;]*?(\d+(?:\.\d+)?)px", match.group(2))
        if font:
            sizes[match.group(1)] = float(font.group(1))
    return sizes


def _font_size(element: ET.Element, sizes: dict[str, float]) -> float:
    explicit = element.get("font-size")
    if explicit:
        return float(explicit.removesuffix("px"))
    for name in (element.get("class") or "").split():
        if name in sizes:
            return sizes[name]
    return 14.0


@pytest.mark.parametrize("diagram", DIAGRAMS)
def test_architecture_diagram_text_stays_inside_the_canvas(diagram: str) -> None:
    path = _architecture_dir() / diagram
    assert path.exists(), f"Missing architecture diagram: {diagram}"

    source = path.read_text(encoding="utf-8")
    sizes = _class_font_sizes(source)
    root = ET.fromstring(source)

    _, _, width, height = (float(value) for value in root.get("viewBox", "0 0 0 0").split())

    for element in root.iter(f"{SVG_NS}text"):
        value = "".join(element.itertext()).strip()
        if not value:
            continue
        x = float(element.get("x", 0))
        y = float(element.get("y", 0))
        right = x + _text_width(value, _font_size(element, sizes))

        assert right <= width - 4, f"{diagram}: text overflows the canvas: {value}"
        assert y <= height - 2, f"{diagram}: text sits below the canvas: {value}"


@pytest.mark.parametrize("diagram", DIAGRAMS)
def test_architecture_diagram_text_stays_inside_its_box(diagram: str) -> None:
    """Labels must not spill across the border of the box that contains them."""
    path = _architecture_dir() / diagram
    source = path.read_text(encoding="utf-8")
    sizes = _class_font_sizes(source)
    root = ET.fromstring(source)

    boxes = [
        (
            float(rect.get("x", 0)),
            float(rect.get("y", 0)),
            float(rect.get("width", 0)),
            float(rect.get("height", 0)),
        )
        for rect in root.iter(f"{SVG_NS}rect")
        if "bg" not in (rect.get("class") or "")
    ]

    for element in root.iter(f"{SVG_NS}text"):
        value = "".join(element.itertext()).strip()
        if not value:
            continue
        x = float(element.get("x", 0))
        y = float(element.get("y", 0))
        right = x + _text_width(value, _font_size(element, sizes))

        # Boxes nest, so measure against the tightest one that contains the anchor.
        containing = [
            box
            for box in boxes
            if box[0] <= x <= box[0] + box[2] and box[1] <= y <= box[1] + box[3]
        ]
        if not containing:
            continue
        box_x, _, box_width, _ = min(containing, key=lambda box: box[2] * box[3])
        assert right <= box_x + box_width - 4, f"{diagram}: text escapes its box: {value}"


def test_readme_embeds_the_three_architecture_views() -> None:
    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")

    for diagram in DIAGRAMS:
        assert f"docs/architecture/{diagram}" in readme, f"README does not embed {diagram}"

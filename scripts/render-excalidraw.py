from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _font_candidates() -> list[str]:
    return [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]


def _load_font(size: int) -> ImageFont.ImageFont:
    for candidate in _font_candidates():
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _element_bbox(element: dict) -> tuple[float, float, float, float]:
    element_type = element.get("type")
    x = float(element.get("x", 0.0))
    y = float(element.get("y", 0.0))

    if element_type in {"rectangle", "text"}:
        width = float(element.get("width", 0.0))
        height = float(element.get("height", 0.0))
        return (x, y, x + width, y + height)

    if element_type == "arrow":
        points = element.get("points") or []
        if not points:
            return (x, y, x, y)
        absolute = [(x + float(px), y + float(py)) for px, py in points]
        xs = [point[0] for point in absolute]
        ys = [point[1] for point in absolute]
        return (min(xs), min(ys), max(xs), max(ys))

    return (x, y, x, y)


def _compute_canvas_size(
    elements: list[dict],
    min_width: int,
    min_height: int,
) -> tuple[int, int, float, float]:
    if not elements:
        return (min_width, min_height, 0.0, 0.0)

    boxes = [_element_bbox(element) for element in elements]
    min_x = min(box[0] for box in boxes)
    min_y = min(box[1] for box in boxes)
    max_x = max(box[2] for box in boxes)
    max_y = max(box[3] for box in boxes)

    padding = 40
    width = max(min_width, int(math.ceil(max_x - min_x + padding * 2)))
    height = max(min_height, int(math.ceil(max_y - min_y + padding * 2)))
    shift_x = padding - min_x
    shift_y = padding - min_y
    return (width, height, shift_x, shift_y)


def _stroke_color(element: dict, default: str = "#111827") -> str:
    color = element.get("strokeColor")
    return color if isinstance(color, str) else default


def _fill_color(element: dict) -> str | None:
    color = element.get("backgroundColor")
    if isinstance(color, str) and color not in {"transparent", "none"}:
        return color
    return None


def _catmull_rom(points: list[tuple[float, float]], steps: int = 24) -> list[tuple[float, float]]:
    if len(points) < 4:
        return points

    smooth: list[tuple[float, float]] = []
    for index in range(1, len(points) - 2):
        p0 = points[index - 1]
        p1 = points[index]
        p2 = points[index + 1]
        p3 = points[index + 2]
        for step in range(steps):
            t = step / steps
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * (
                2 * p1[0]
                + (-p0[0] + p2[0]) * t
                + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
            )
            y = 0.5 * (
                2 * p1[1]
                + (-p0[1] + p2[1]) * t
                + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
            )
            smooth.append((x, y))
    smooth.append(points[-2])
    smooth.append(points[-1])
    return smooth


def _arrow_points(element: dict, shift_x: float, shift_y: float) -> list[tuple[float, float]]:
    base_x = float(element.get("x", 0.0)) + shift_x
    base_y = float(element.get("y", 0.0)) + shift_y
    points = element.get("points") or []
    absolute = [(base_x + float(px), base_y + float(py)) for px, py in points]
    if len(absolute) >= 3 and element.get("roundness", {}).get("type") == 2:
        padded = [absolute[0], *absolute, absolute[-1]]
        return _catmull_rom(padded)
    return absolute


def _draw_arrowhead(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    color: str,
    width: int,
) -> None:
    if len(points) < 2:
        return
    end = points[-1]
    prev = points[-2]
    dx = end[0] - prev[0]
    dy = end[1] - prev[1]
    magnitude = math.hypot(dx, dy)
    if magnitude < 0.1:
        return

    ux = dx / magnitude
    uy = dy / magnitude
    size = max(10.0, width * 3.0)
    angle = math.radians(28)

    def _rotate(vec_x: float, vec_y: float, theta: float) -> tuple[float, float]:
        return (
            vec_x * math.cos(theta) - vec_y * math.sin(theta),
            vec_x * math.sin(theta) + vec_y * math.cos(theta),
        )

    left = _rotate(-ux, -uy, angle)
    right = _rotate(-ux, -uy, -angle)
    p2 = (end[0] + left[0] * size, end[1] + left[1] * size)
    p3 = (end[0] + right[0] * size, end[1] + right[1] * size)
    draw.polygon([end, p2, p3], fill=color)


def _line_metrics(font: ImageFont.ImageFont, line: str) -> tuple[float, float]:
    sample = line if line else " "
    if hasattr(font, "getbbox"):
        left, top, right, bottom = font.getbbox(sample)
        width = float(max(0, right - left))
        height = float(max(1, bottom - top))
    else:
        width, height = font.getsize(sample)
        width = float(width)
        height = float(max(1, height))
    if not line:
        return (0.0, height)
    return (width, height)


def _layout_multiline_text(
    draw: ImageDraw.ImageDraw | None,
    text: str,
    font: ImageFont.ImageFont,
    box_x: float,
    box_y: float,
    box_w: float,
    box_h: float,
    spacing: int,
) -> tuple[list[str], list[tuple[float, float]], float]:
    del draw  # The layout uses font metrics only and is deterministic.
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n") if normalized else [""]

    widths: list[float] = []
    heights: list[float] = []
    for line in lines:
        width, height = _line_metrics(font, line)
        widths.append(width)
        heights.append(height)

    if not heights:
        return ([], [], 0.0)

    total_height = sum(heights) + spacing * max(0, len(lines) - 1)
    start_y = box_y + max(0.0, (box_h - total_height) / 2.0)

    starts: list[tuple[float, float]] = []
    cursor_y = start_y
    for index, _line in enumerate(lines):
        line_w = widths[index]
        line_h = heights[index]
        line_x = box_x + max(0.0, (box_w - line_w) / 2.0)
        starts.append((line_x, cursor_y))
        cursor_y += line_h + spacing
    return (lines, starts, total_height)


def _draw_rectangles(
    draw: ImageDraw.ImageDraw,
    elements: Iterable[dict],
    shift_x: float,
    shift_y: float,
) -> None:
    for element in elements:
        if element.get("type") != "rectangle":
            continue
        x = float(element.get("x", 0.0)) + shift_x
        y = float(element.get("y", 0.0)) + shift_y
        width = float(element.get("width", 0.0))
        height = float(element.get("height", 0.0))
        stroke_width = int(element.get("strokeWidth", 2))
        radius = 12
        draw.rounded_rectangle(
            [x, y, x + width, y + height],
            radius=radius,
            outline=_stroke_color(element),
            fill=_fill_color(element),
            width=stroke_width,
        )


def _draw_arrows(
    draw: ImageDraw.ImageDraw,
    elements: Iterable[dict],
    shift_x: float,
    shift_y: float,
) -> None:
    for element in elements:
        if element.get("type") != "arrow":
            continue
        points = _arrow_points(element, shift_x, shift_y)
        if len(points) < 2:
            continue
        color = _stroke_color(element)
        width = int(element.get("strokeWidth", 2))
        draw.line(points, fill=color, width=width, joint="curve")
        _draw_arrowhead(draw, points, color, width)


def _draw_text(
    draw: ImageDraw.ImageDraw,
    elements: Iterable[dict],
    shift_x: float,
    shift_y: float,
) -> None:
    for element in elements:
        if element.get("type") != "text":
            continue
        text = element.get("text")
        if not isinstance(text, str):
            continue
        x = float(element.get("x", 0.0)) + shift_x
        y = float(element.get("y", 0.0)) + shift_y
        width = float(element.get("width", 0.0))
        height = float(element.get("height", 0.0))
        font_size = int(element.get("fontSize", 20))
        font = _load_font(font_size)
        spacing = max(4, int(round(font_size * 0.2)))
        lines, starts, _ = _layout_multiline_text(
            draw=draw,
            text=text,
            font=font,
            box_x=x,
            box_y=y,
            box_w=width,
            box_h=height,
            spacing=spacing,
        )
        color = _stroke_color(element)
        for line, (line_x, line_y) in zip(lines, starts):
            draw.text((line_x, line_y), line, fill=color, font=font)


def render_excalidraw(
    source: Path,
    output: Path,
    min_width: int,
    min_height: int,
) -> tuple[int, int]:
    data = _load_json(source)
    elements = data.get("elements")
    if not isinstance(elements, list):
        raise ValueError("Invalid Excalidraw JSON: missing elements array")

    width, height, shift_x, shift_y = _compute_canvas_size(elements, min_width, min_height)
    image = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)

    _draw_rectangles(draw, elements, shift_x, shift_y)
    _draw_arrows(draw, elements, shift_x, shift_y)
    _draw_text(draw, elements, shift_x, shift_y)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG")
    return (width, height)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a basic Excalidraw JSON diagram to PNG")
    parser.add_argument("source", type=Path, help="Path to .excalidraw JSON file")
    parser.add_argument("output", type=Path, help="Path to output PNG file")
    parser.add_argument("--min-width", type=int, default=1400)
    parser.add_argument("--min-height", type=int, default=800)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    width, height = render_excalidraw(args.source, args.output, args.min_width, args.min_height)
    print(f"Rendered {args.output} ({width}x{height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

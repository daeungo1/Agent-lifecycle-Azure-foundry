from __future__ import annotations

import re
from pathlib import Path


def _infra_path(*parts: str) -> Path:
    return Path(__file__).resolve().parents[1].joinpath("infra", *parts)


def _extract_search_services_keys(bicepparam_text: str) -> list[str]:
    marker = "param searchServices = {"
    start = bicepparam_text.find(marker)
    if start == -1:
        raise AssertionError("searchServices object parameter was not found")

    pos = start + len(marker)
    depth = 1
    body_chars: list[str] = []
    while pos < len(bicepparam_text) and depth > 0:
        char = bicepparam_text[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                break
        if depth > 0:
            body_chars.append(char)
        pos += 1

    if depth != 0:
        raise AssertionError("searchServices object parameter is not closed")

    body = "".join(body_chars)
    return re.findall(r"^\s{2}([A-Za-z][A-Za-z0-9]*)\s*:\s*\{", body, flags=re.MULTILINE)


def test_named_search_endpoint_outputs_do_not_use_numeric_module_index() -> None:
    main_bicep = _infra_path("main.bicep").read_text(encoding="utf-8")
    index_ref_pattern = (
        r"output\s+FOUNDRYIQ_SEARCH_ENDPOINT_[A-Z_]+\s+string\s*=\s*.*\[[0-9]+\]"
    )
    assert re.search(index_ref_pattern, main_bicep) is None


def test_main_bicepparam_uses_exactly_four_keyed_search_boundaries() -> None:
    main_bicepparam = _infra_path("main.bicepparam").read_text(encoding="utf-8")
    keys = _extract_search_services_keys(main_bicepparam)
    assert keys == ["shared", "development", "humanResources", "marketing"]

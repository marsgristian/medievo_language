from __future__ import annotations

import json
from typing import Any, Literal

NormalizationMode = Literal["line_min", "char_min", "min", "human"]


def normalize_document(data: Any, normalization: str | None = "line_min") -> str:
    if normalization is None:
        return ""

    mode = normalization.lower()
    if mode not in {"line_min", "char_min", "min", "human"}:
        raise ValueError(f"Normalization desconhecida: {normalization}")

    document = _extract_document(data)
    if document is None:
        return ""

    if mode == "human":
        return _render_document(document, compact=False)

    if mode == "line_min":
        return _render_document(document, compact=False)

    return _render_document(document, compact=True)


def _extract_document(data: Any) -> dict[str, Any] | None:
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return None

    if not isinstance(data, dict):
        return None

    if isinstance(data.get("object"), dict):
        obj = data["object"]
        if isinstance(obj.get("document"), dict):
            return obj["document"]

    if isinstance(data.get("document"), dict):
        return data["document"]

    if isinstance(data.get("sections"), list):
        return data

    return None


def _render_document(document: dict[str, Any], *, compact: bool) -> str:
    sections = document.get("sections") or []
    if not isinstance(sections, list):
        return ""

    rendered = [_render_section(section, compact=compact) for section in sections if isinstance(section, dict)]
    return "\n".join(part for part in rendered if part).strip()


def _render_section(section: dict[str, Any], *, compact: bool) -> str:
    name = section.get("section_name") or ""
    if not name:
        return ""

    section_value = section.get("section_value")
    sep = ":" if compact else ": "
    header = f"#{name}"
    if section_value:
        header = f"{header}{sep}{section_value}"

    lines = [header]
    items = [item for item in section.get("items", []) if isinstance(item, dict)]
    states = [state for state in section.get("states", []) if isinstance(state, dict)]
    state_names = [state.get("subsec_name") for state in states if state.get("subsec_name")]

    ungrouped = [item for item in items if not item.get("state")]
    if ungrouped:
        lines.append(_join_items(ungrouped, compact=compact))

    for state_name in state_names:
        state_items = [item for item in items if item.get("state") == state_name]
        if state_items:
            marker = ">" if compact else "> "
            lines.append(f"{marker}{state_name}{sep}{_join_items(state_items, compact=compact)}")
        else:
            marker = ">" if compact else "> "
            lines.append(f"{marker}{state_name}:")

    remaining_states = sorted(
        {
            item.get("state")
            for item in items
            if item.get("state") and item.get("state") not in state_names
        }
    )
    for state_name in remaining_states:
        state_items = [item for item in items if item.get("state") == state_name]
        marker = ">" if compact else "> "
        lines.append(f"{marker}{state_name}{sep}{_join_items(state_items, compact=compact)}")

    return "\n".join(line for line in lines if line)


def _join_items(items: list[dict[str, Any]], *, compact: bool) -> str:
    separator = "|" if compact else " | "
    return separator.join(_render_item(item, compact=compact) for item in items)


def _render_item(item: dict[str, Any], *, compact: bool) -> str:
    raw_text = item.get("raw_text")
    if isinstance(raw_text, str) and raw_text.strip():
        return _compact_item_text(raw_text) if compact else " ".join(raw_text.strip().split())

    key = item.get("key")
    values = item.get("values") or []
    value_texts = []
    if isinstance(values, list):
        value_texts = [value.get("value") for value in values if isinstance(value, dict) and value.get("value")]

    children = item.get("children") or []
    child_texts = []
    if isinstance(children, list):
        child_texts = [_render_item(child, compact=compact) for child in children if isinstance(child, dict)]

    value_separator = ";" if compact else "; "
    body = value_separator.join([*value_texts, *child_texts])
    if key:
        sep = ":" if compact else ": "
        return f"{key}{sep}{body}".strip()
    return body


def _compact_item_text(text: str) -> str:
    compacted = " ".join(text.strip().split())
    compacted = compacted.replace(" | ", "|")
    compacted = compacted.replace("; ", ";")
    compacted = compacted.replace(": ", ":")
    return compacted

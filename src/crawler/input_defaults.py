from __future__ import annotations

import json
from typing import Any

InputDefaults = dict[str, dict[str, Any]]


def empty_input_defaults() -> InputDefaults:
    return {"field_patterns": {}, "type_fallbacks": {}}


def normalize_input_defaults(value: dict[str, Any] | None) -> InputDefaults:
    if not isinstance(value, dict):
        return empty_input_defaults()

    if "field_patterns" in value or "type_fallbacks" in value:
        field_patterns = value.get("field_patterns", {})
        type_fallbacks = value.get("type_fallbacks", {})
        return {
            "field_patterns": dict(field_patterns) if isinstance(field_patterns, dict) else {},
            "type_fallbacks": dict(type_fallbacks) if isinstance(type_fallbacks, dict) else {},
        }

    return {"field_patterns": dict(value), "type_fallbacks": {}}


def load_input_defaults(path: str | None) -> InputDefaults:
    if not path:
        return empty_input_defaults()

    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    return normalize_input_defaults(raw if isinstance(raw, dict) else None)


def merge_input_defaults(base: dict[str, Any] | None, override: dict[str, Any] | None) -> InputDefaults:
    normalized_base = normalize_input_defaults(base)
    normalized_override = normalize_input_defaults(override)

    return {
        "field_patterns": {
            **normalized_base["field_patterns"],
            **normalized_override["field_patterns"],
        },
        "type_fallbacks": {
            **normalized_base["type_fallbacks"],
            **normalized_override["type_fallbacks"],
        },
    }


def resolve_input_defaults(config_path: str | None, override: dict[str, Any] | None = None) -> InputDefaults:
    return merge_input_defaults(load_input_defaults(config_path), override)

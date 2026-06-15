from __future__ import annotations

import json
import re
from typing import Any


class InputValueResolver:
    def __init__(
        self,
        config_path: str | None = None,
        input_defaults: dict[str, Any] | None = None,
    ):
        self._config = input_defaults if isinstance(input_defaults, dict) else self._load_config(config_path)

        if "field_patterns" in self._config:
            normalized_patterns = {}
            for k, v in self._config["field_patterns"].items():
                norm_k = re.sub(r"[\s_\-]", "", str(k).lower())
                if norm_k:
                    normalized_patterns[norm_k] = v
            self._config["field_patterns"] = normalized_patterns

    def _load_config(self, path: str | None) -> dict[str, Any]:
        if not path:
            return {"field_patterns": {}, "type_fallbacks": {}}

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def resolve(self, element: dict) -> str:
        hint_keys = [
            element.get("id", ""),
            element.get("name", ""),
            element.get("placeholder", ""),
            element.get("label", ""),
        ]

        patterns = self._config.get("field_patterns", {})
        best_value: str | None = None
        best_len = -1

        for key in hint_keys:
            if not key:
                continue

            normalized = re.sub(r"[\s_\-]", "", str(key).lower())

            for pattern, value in patterns.items():
                if pattern and pattern in normalized:
                    if len(pattern) > best_len:
                        best_value = str(value)
                        best_len = len(pattern)

        if best_value is not None:
            return self._apply_constraints(best_value, element)

        fallbacks = self._config.get("type_fallbacks", {})
        fallback = str(fallbacks.get(element.get("type", "text"), "test"))

        tag = str(element.get("tag", "") or element.get("type", "")).lower()
        if tag == "select":
            options = element.get("options", [])
            if options:
                for opt in options:
                    val = str(opt if isinstance(opt, str) else opt.get("value", ""))
                    if val and val.strip() and val.lower() not in ("none", "null", ""):
                        return val

                first = options[0]
                return str(first if isinstance(first, str) else first.get("value", ""))

        return self._apply_constraints(fallback, element)

    def _apply_constraints(self, value: str, element: dict) -> str:
        t = str(element.get("type", "") or "").lower()
        maxlength = element.get("maxlength")

        if maxlength is not None:
            try:
                ml = int(maxlength)
                if ml >= 0:
                    value = value[:ml]
            except Exception:
                pass

        if t in ("number", "range"):
            chosen = None
            min_v = element.get("min")
            max_v = element.get("max")
            try:
                if min_v is not None:
                    chosen = str(int(float(min_v)))
            except Exception:
                chosen = None

            if chosen is None:
                try:
                    if max_v is not None:
                        chosen = str(int(float(max_v)))
                except Exception:
                    chosen = None

            if chosen is not None:
                value = chosen

        return value

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")
_HTTP_SCHEME_RE = re.compile(r"https?://", re.IGNORECASE)


def normalize_semantic_text(value: Any) -> str:
    text = _HTTP_SCHEME_RE.sub(
        "//",
        str(value or "").replace("_", " ").replace("-", " ").lower(),
    )
    return _WHITESPACE_RE.sub(" ", text).strip()


class FeatureExtractor(ABC):
    @abstractmethod
    def extract(self, element: dict[str, Any]) -> str:
        pass


class DOMFeatureExtractor(FeatureExtractor):
    TEXT_KEYS = (
        "tag",
        "type",
        "id",
        "name",
        "text",
        "value",
        "placeholder",
        "label",
        "aria_label",
        "aria-label",
        "role",
        "title",
        "href",
        "aria_invalid",
        "aria_expanded",
    )

    def extract(self, element: dict[str, Any]) -> str:
        features: list[str] = []
        for key in self.TEXT_KEYS:
            value = normalize_semantic_text(element.get(key))
            if value:
                features.append(value)

        options = element.get("options") or []
        for option in options[:20]:
            if isinstance(option, dict):
                option_text = normalize_semantic_text(
                    option.get("text") or option.get("value")
                )
            else:
                option_text = normalize_semantic_text(option)
            if option_text:
                features.append(option_text)

        return " ".join(dict.fromkeys(features))

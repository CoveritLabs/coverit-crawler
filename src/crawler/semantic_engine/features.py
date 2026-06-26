from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from src.crawler.semantic_engine.extractor import DOMFeatureExtractor
from src.crawler.semantic_engine.topic import TopicClassifier

STRUCTURAL_KEYS = (
    "disabled",
    "readonly",
    "required",
    "checked",
    "contenteditable",
    "in_form",
    "aria_invalid",
    "aria_expanded",
)


class ElementFeatureEncoder(Protocol):
    @property
    def dimension(self) -> int:
        ...

    def encode(self, elements: list[dict[str, Any]]) -> np.ndarray:
        ...


class ManualElementFeatureEncoder:
    def __init__(
        self,
        text_encoder: Any,
        *,
        topic_classifier: TopicClassifier | None = None,
        extractor: DOMFeatureExtractor | None = None,
    ):
        self._text_encoder = text_encoder
        self._topic_classifier = topic_classifier
        self._extractor = extractor or DOMFeatureExtractor()
        self._dimension = (
            int(getattr(text_encoder, "dimension", 0))
            + len(self._structural_vector({}))
            + (len(topic_classifier.classes) if topic_classifier is not None else 0)
        )

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, elements: list[dict[str, Any]]) -> np.ndarray:
        if not elements:
            dimension = getattr(self, "_dimension", 0)
            return np.empty((0, dimension), dtype=float)

        texts = [self._extractor.extract(element) for element in elements]
        text_features = self._text_encoder.transform(texts)
        structural = np.asarray(
            [self._structural_vector(element) for element in elements],
            dtype=float,
        )
        topic_features = self._topic_vectors(elements)
        combined = np.hstack([np.asarray(text_features), structural, topic_features])
        norms = np.linalg.norm(combined, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return combined / norms

    def _topic_vectors(self, elements: list[dict[str, Any]]) -> np.ndarray:
        if self._topic_classifier is None:
            return np.empty((len(elements), 0), dtype=float)

        classes = self._topic_classifier.classes
        rows = []
        for element in elements:
            prediction = self._topic_classifier.predict(element)
            rows.append(
                [prediction.probabilities.get(label, 0.0) for label in classes]
            )
        return np.asarray(rows, dtype=float)

    def _structural_vector(self, element: dict[str, Any]) -> list[float]:
        tag = str(element.get("tag", "") or "").lower()
        input_type = str(element.get("type", "") or "").lower()
        role = str(element.get("role", "") or "").lower()
        options = element.get("options") or []

        categories = [
            tag == "input",
            tag == "textarea",
            tag == "select",
            tag == "button",
            tag == "a",
            input_type in {"text", "search", "email", "password", "tel", "url"},
            input_type in {"checkbox", "radio"},
            role == "button",
        ]
        flags = [bool(element.get(key)) for key in STRUCTURAL_KEYS]
        return [float(value) for value in categories + flags] + [
            min(len(options), 50) / 50.0
        ]

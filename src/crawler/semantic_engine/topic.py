from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from src.crawler.semantic_engine.extractor import DOMFeatureExtractor

TOPIC_ALIASES = {
    "company": "organization",
    "query": "search",
}


def canonical_topic(topic: str) -> str:
    normalized = str(topic or "").strip().lower()
    return TOPIC_ALIASES.get(normalized, normalized)


@dataclass(frozen=True)
class TopicPrediction:
    topic: str | None
    confidence: float
    probabilities: dict[str, float]
    abstained: bool


class TopicClassifier(Protocol):
    @property
    def classes(self) -> tuple[str, ...]:
        ...

    def predict(self, element: dict[str, Any]) -> TopicPrediction:
        ...


class ManualTopicClassifier:
    def __init__(
        self,
        model: Any,
        *,
        thresholds: dict[str, float] | None = None,
        default_threshold: float = 0.55,
        extractor: DOMFeatureExtractor | None = None,
    ):
        self._model = model
        self._thresholds = thresholds or {}
        self._default_threshold = default_threshold
        self._extractor = extractor or DOMFeatureExtractor()
        self._classes = tuple(canonical_topic(label) for label in model.classes_)

    @property
    def classes(self) -> tuple[str, ...]:
        return self._classes

    def predict(self, element: dict[str, Any]) -> TopicPrediction:
        text = self._extractor.extract(element)
        if not text:
            return TopicPrediction(None, 0.0, {}, True)

        probabilities = self._model.predict_proba([text])[0]
        best_index = int(np.argmax(probabilities))
        topic = self._classes[best_index]
        confidence = float(probabilities[best_index])
        threshold = float(self._thresholds.get(topic, self._default_threshold))
        probability_map = {
            label: float(probability)
            for label, probability in zip(self._classes, probabilities, strict=True)
        }

        return TopicPrediction(
            topic=None if confidence < threshold else topic,
            confidence=confidence,
            probabilities=probability_map,
            abstained=confidence < threshold,
        )

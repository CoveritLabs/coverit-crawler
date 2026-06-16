from dataclasses import dataclass
from typing import Any

from src.crawler.semantic_engine.extractor import FeatureExtractor, normalize_semantic_text
from src.crawler.semantic_engine.topic import TopicClassifier, canonical_topic


@dataclass(frozen=True)
class ResolvedInput:
    matched_key: str
    value: Any
    confidence: float
    predicted_topic: str | None = None
    abstained: bool = False


class InputResolver:
    def __init__(
        self,
        extractor: FeatureExtractor,
        classifier: TopicClassifier | None,
        input_defaults: dict[str, Any],
    ):
        self._extractor = extractor
        self._input_defaults = input_defaults
        self._classifier = classifier
        self._canonical_defaults = {
            canonical_topic(key): value for key, value in input_defaults.items()
        }

    def resolve(self, element: dict[str, Any]) -> ResolvedInput | None:
        if not self._input_defaults:
            return None

        deterministic = self._deterministic_match(element)
        if deterministic is not None:
            return deterministic

        if self._classifier is None:
            return None
        prediction = self._classifier.predict(element)
        if prediction.abstained or prediction.topic is None:
            return ResolvedInput(
                matched_key="",
                value=None,
                confidence=prediction.confidence,
                predicted_topic=None,
                abstained=True,
            )

        topic = canonical_topic(prediction.topic)
        if topic not in self._canonical_defaults:
            return None

        return ResolvedInput(
            matched_key=topic,
            value=self._canonical_defaults[topic],
            confidence=prediction.confidence,
            predicted_topic=topic,
        )

    def _deterministic_match(
        self,
        element: dict[str, Any],
    ) -> ResolvedInput | None:
        hints = {
            normalize_semantic_text(element.get(key))
            for key in ("type", "name", "id", "placeholder", "label", "aria_label")
        }
        hints.discard("")

        for key, value in self._input_defaults.items():
            normalized_key = normalize_semantic_text(key)
            if normalized_key and any(
                normalized_key == hint
                or normalized_key in hint.split()
                for hint in hints
            ):
                return ResolvedInput(
                    matched_key=key,
                    value=value,
                    confidence=1.0,
                    predicted_topic=canonical_topic(key),
                )
        return None

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.crawler.semantic_engine.artifacts import ArtifactError, ModelArtifactLoader
from src.crawler.semantic_engine.extractor import DOMFeatureExtractor
from src.crawler.semantic_engine.features import SklearnElementFeatureEncoder
from src.crawler.semantic_engine.resolver import InputResolver, ResolvedInput
from src.crawler.semantic_engine.state import (
    PairFeatureEquivalenceClassifier,
    StateComparisonBank,
    StateComparisonResult,
    StateProfiler,
    StateSemanticProfile,
)
from src.crawler.semantic_engine.topic import SklearnTopicClassifier, TopicClassifier

logger = logging.getLogger(__name__)


class SemanticEngine:
    def __init__(
        self,
        input_defaults: dict[str, Any],
        *,
        artifact_dir: str | Path,
        enabled: bool = True,
        similarity_threshold: float = 0.9,
        uncertainty_margin: float = 0.05,
        max_bank_size: int = 1000,
        topic_classifier: TopicClassifier | None = None,
        comparison_bank: StateComparisonBank | None = None,
    ):
        self.extractor = DOMFeatureExtractor()
        self._enabled = enabled
        self._load_error: str | None = None
        self._topic_classifier = topic_classifier
        self._comparison_bank = comparison_bank

        if topic_classifier is None or (enabled and comparison_bank is None):
            self._load_artifacts(
                artifact_dir=artifact_dir,
                threshold=similarity_threshold,
                uncertainty_margin=uncertainty_margin,
                max_bank_size=max_bank_size,
            )

        self.resolver = InputResolver(
            extractor=self.extractor,
            classifier=self._topic_classifier,
            input_defaults=input_defaults,
        )

    @property
    def available(self) -> bool:
        return self._enabled and self._comparison_bank is not None

    @property
    def load_error(self) -> str | None:
        return self._load_error

    @property
    def profile_count(self) -> int:
        return (
            self._comparison_bank.profile_count
            if self._comparison_bank is not None
            else 0
        )

    def resolve_input_value(
        self,
        element: dict[str, Any],
    ) -> ResolvedInput | None:
        return self.resolver.resolve(element)

    def configure_input_defaults(self, input_defaults: dict[str, Any]) -> None:
        self.resolver = InputResolver(
            extractor=self.extractor,
            classifier=self._topic_classifier,
            input_defaults=input_defaults,
        )

    def register_state(
        self,
        state_hash: str,
        elements: list[dict[str, Any]],
    ) -> StateComparisonResult:
        if not self.available:
            return StateComparisonResult(
                state_hash,
                True,
                False,
                None,
                0.0,
                {},
                "semantic_engine_unavailable",
            )

        try:
            return self._comparison_bank.register(state_hash, elements)
        except Exception:
            logger.exception("Semantic state comparison failed open")
            return StateComparisonResult(
                state_hash,
                True,
                False,
                None,
                0.0,
                {},
                "comparison_error",
            )

    def get_state_profile(
        self,
        state_hash: str,
    ) -> StateSemanticProfile | None:
        if self._comparison_bank is None:
            return None
        return self._comparison_bank.get_profile(state_hash)

    def explain_comparison(
        self,
        comparison: StateComparisonResult,
    ) -> dict[str, Any]:
        if self._comparison_bank is None:
            return {}
        return self._comparison_bank.explain_result(comparison)

    def _load_artifacts(
        self,
        *,
        artifact_dir: str | Path,
        threshold: float,
        uncertainty_margin: float,
        max_bank_size: int,
    ) -> None:
        loader = ModelArtifactLoader(artifact_dir)
        try:
            topic_bundle = loader.load("topic_model.joblib", "topic_classifier")
            topic_classifier = SklearnTopicClassifier(
                topic_bundle.payload["pipeline"],
                thresholds=topic_bundle.payload.get("thresholds"),
                default_threshold=float(
                    topic_bundle.payload.get("default_threshold", 0.55)
                ),
                extractor=self.extractor,
            )

            self._topic_classifier = topic_classifier
        except (ArtifactError, KeyError, TypeError, ValueError) as exc:
            self._load_error = str(exc)
            logger.warning("Topic classifier unavailable: %s", exc)
            return

        if not self._enabled:
            return

        try:
            state_bundle = loader.load(
                "state_equivalence.joblib",
                "state_equivalence",
            )
            encoder = SklearnElementFeatureEncoder(
                state_bundle.payload["text_pipeline"],
                topic_classifier=topic_classifier,
                extractor=self.extractor,
            )
            profiler = StateProfiler(encoder, topic_classifier)
            classifier = PairFeatureEquivalenceClassifier(
                state_bundle.payload["pair_classifier"]
            )
            self._comparison_bank = StateComparisonBank(
                profiler,
                classifier,
                threshold=threshold,
                uncertainty_margin=uncertainty_margin,
                max_size=max_bank_size,
            )
        except (ArtifactError, KeyError, TypeError, ValueError) as exc:
            self._load_error = str(exc)
            logger.warning("State equivalence unavailable: %s", exc)

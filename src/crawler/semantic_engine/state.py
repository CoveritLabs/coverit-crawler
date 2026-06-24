from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from src.crawler.semantic_engine.features import ElementFeatureEncoder
from src.crawler.semantic_engine.topic import TopicClassifier

PAIR_FEATURE_NAMES = (
    "element_similarity",
    "pooled_similarity",
    "topic_similarity",
    "structure_similarity",
    "count_similarity",
)

HIGH_SIMILARITY_EQUIVALENCE_MINIMUMS = {
    "element_similarity": 0.995,
    "pooled_similarity": 0.995,
    "topic_similarity": 0.995,
    "structure_similarity": 0.98,
    "count_similarity": 0.95,
}

SEMANTIC_PRIORITY_NOVEL = 0.0
SEMANTIC_PRIORITY_EQUIVALENT = 1.0


@dataclass(frozen=True, eq=False)
class StateSemanticProfile:
    state_hash: str
    element_vectors: np.ndarray
    pooled_vector: np.ndarray
    topic_distribution: np.ndarray
    structural_distribution: np.ndarray
    element_count: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "state_hash": self.state_hash,
            "element_vectors": self.element_vectors.tolist(),
            "pooled_vector": self.pooled_vector.tolist(),
            "topic_distribution": self.topic_distribution.tolist(),
            "structural_distribution": self.structural_distribution.tolist(),
            "element_count": self.element_count,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> StateSemanticProfile | None:
        try:
            return cls(
                state_hash=str(payload.get("state_hash") or ""),
                element_vectors=np.asarray(payload.get("element_vectors") or [], dtype=float),
                pooled_vector=np.asarray(payload.get("pooled_vector") or [], dtype=float),
                topic_distribution=np.asarray(payload.get("topic_distribution") or [], dtype=float),
                structural_distribution=np.asarray(payload.get("structural_distribution") or [], dtype=float),
                element_count=int(payload.get("element_count") or 0),
            )
        except Exception:
            return None

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, StateSemanticProfile)
            and self.state_hash == other.state_hash
        )

    def __hash__(self) -> int:
        return hash(self.state_hash)


@dataclass(frozen=True)
class StateComparisonResult:
    state_hash: str
    is_novel: bool
    is_equivalent: bool
    matched_state_hash: str | None
    confidence: float
    scores: dict[str, float]
    reason: str


def semantic_priority_penalty(result: StateComparisonResult) -> float:
    if result.reason in {"semantic_engine_unavailable", "comparison_error"}:
        return SEMANTIC_PRIORITY_NOVEL
    if result.reason == "already_registered":
        return SEMANTIC_PRIORITY_NOVEL
    if result.is_equivalent:
        return SEMANTIC_PRIORITY_EQUIVALENT
    if not result.matched_state_hash:
        return SEMANTIC_PRIORITY_NOVEL
    return float(np.clip(result.confidence, 0.0, SEMANTIC_PRIORITY_EQUIVALENT))


class StateProfiler:
    def __init__(
        self,
        encoder: ElementFeatureEncoder,
        topic_classifier: TopicClassifier | None = None,
    ):
        self._encoder = encoder
        self._topic_classifier = topic_classifier

    def profile(
        self,
        state_hash: str,
        elements: list[dict[str, Any]],
    ) -> StateSemanticProfile:
        vectors = self._encoder.encode(elements)
        pooled = (
            vectors.mean(axis=0)
            if vectors.shape[0]
            else np.zeros(self._encoder.dimension, dtype=float)
        )
        pooled_norm = np.linalg.norm(pooled)
        if pooled_norm:
            pooled = pooled / pooled_norm

        return StateSemanticProfile(
            state_hash=state_hash,
            element_vectors=vectors,
            pooled_vector=pooled,
            topic_distribution=self._topic_distribution(elements),
            structural_distribution=self._structural_distribution(elements),
            element_count=len(elements),
        )

    def _topic_distribution(
        self,
        elements: list[dict[str, Any]],
    ) -> np.ndarray:
        if self._topic_classifier is None:
            return np.empty(0, dtype=float)

        classes = self._topic_classifier.classes
        distribution = np.zeros(len(classes), dtype=float)
        for element in elements:
            prediction = self._topic_classifier.predict(element)
            distribution += np.asarray(
                [prediction.probabilities.get(label, 0.0) for label in classes]
            )
        return _normalize(distribution)

    def _structural_distribution(
        self,
        elements: list[dict[str, Any]],
    ) -> np.ndarray:
        buckets = np.zeros(12, dtype=float)
        for element in elements:
            tag = str(element.get("tag", "") or "").lower()
            input_type = str(element.get("type", "") or "").lower()
            index = {
                "input": 0,
                "textarea": 1,
                "select": 2,
                "button": 3,
                "a": 4,
            }.get(tag, 5)
            buckets[index] += 1
            buckets[6] += float(input_type in {"checkbox", "radio"})
            buckets[7] += float(bool(element.get("disabled")))
            buckets[8] += float(bool(element.get("required")))
            buckets[9] += float(bool(element.get("checked")))
            buckets[10] += float(bool(element.get("aria_invalid")))
            buckets[11] += float(bool(element.get("aria_expanded")))
        return _normalize(buckets)


class StateEquivalenceClassifier(Protocol):
    def compare(
        self,
        left: StateSemanticProfile,
        right: StateSemanticProfile,
    ) -> tuple[float, dict[str, float]]:
        ...


class PairFeatureEquivalenceClassifier:
    def __init__(
        self,
        model: Any,
        *,
        equivalent_class: int | bool = 1,
    ):
        self._model = model
        self._equivalent_class = equivalent_class

    def compare(
        self,
        left: StateSemanticProfile,
        right: StateSemanticProfile,
    ) -> tuple[float, dict[str, float]]:
        scores = pair_features(left, right)
        row = np.asarray([[scores[name] for name in PAIR_FEATURE_NAMES]])
        probabilities = self._model.predict_proba(row)[0]
        classes = list(self._model.classes_)
        try:
            index = classes.index(self._equivalent_class)
        except ValueError:
            index = int(np.argmax(classes))
        return float(probabilities[index]), scores

    def explain_scores(self, scores: dict[str, float]) -> dict[str, Any]:
        row = np.asarray([[scores[name] for name in PAIR_FEATURE_NAMES]])
        probabilities = self._model.predict_proba(row)[0]
        classes = list(self._model.classes_)
        try:
            equivalent_index = classes.index(self._equivalent_class)
        except ValueError:
            equivalent_index = int(np.argmax(classes))

        predicted_class = (
            self._model.predict(row)[0]
            if hasattr(self._model, "predict")
            else classes[int(np.argmax(probabilities))]
        )

        return {
            "model_predicted_class": _plain_value(predicted_class),
            "model_equivalent_class": _plain_value(self._equivalent_class),
            "model_equivalent_probability": float(probabilities[equivalent_index]),
            "model_probabilities": {
                str(_plain_value(label)): float(probability)
                for label, probability in zip(classes, probabilities, strict=True)
            },
        }

    def predicts_equivalent(self, scores: dict[str, float]) -> bool:
        row = np.asarray([[scores[name] for name in PAIR_FEATURE_NAMES]])
        if not hasattr(self._model, "predict"):
            return False
        predicted_class = _plain_value(self._model.predict(row)[0])
        return predicted_class == _plain_value(self._equivalent_class)


class StateComparisonBank:
    def __init__(
        self,
        profiler: StateProfiler,
        classifier: StateEquivalenceClassifier,
        *,
        threshold: float,
        uncertainty_margin: float,
        max_size: int,
        graph_store: Any | None = None,
        graph_id: str | None = None,
        session_id: str | None = None,
        batch_size: int = 100,
    ):
        self._profiler = profiler
        self._classifier = classifier
        self._threshold = threshold
        self._uncertainty_margin = uncertainty_margin
        self._max_size = max(1, max_size)
        self._graph_store = graph_store
        self._graph_id = graph_id
        self._session_id = session_id
        self._batch_size = max(1, int(batch_size))
        self._profiles: OrderedDict[str, StateSemanticProfile] = OrderedDict()

    @property
    def profile_count(self) -> int:
        return len(self._profiles)

    @property
    def threshold(self) -> float:
        return self._threshold

    @property
    def uncertainty_margin(self) -> float:
        return self._uncertainty_margin

    @property
    def equivalence_bar(self) -> float:
        return self._threshold + self._uncertainty_margin

    def get_profile(self, state_hash: str) -> StateSemanticProfile | None:
        return self._profiles.get(state_hash)

    def explain_result(self, result: StateComparisonResult) -> dict[str, Any]:
        explanation: dict[str, Any] = {
            "threshold": self._threshold,
            "uncertainty_margin": self._uncertainty_margin,
            "equivalence_bar": self.equivalence_bar,
            "profile_count": self.profile_count,
            "scores": result.scores,
        }
        if result.scores and hasattr(self._classifier, "explain_scores"):
            explain_scores = getattr(self._classifier, "explain_scores", None)
            if callable(explain_scores):
                extra = explain_scores(result.scores)
                if isinstance(extra, dict):
                    explanation.update(extra)
        return explanation

    async def register(
        self,
        state_hash: str,
        elements: list[dict[str, Any]],
    ) -> StateComparisonResult:
        if self._graph_store is not None and self._graph_id:
            return await self._register_persisted(state_hash, elements)
        return self._register_local(state_hash, elements)

    async def _register_persisted(
        self,
        state_hash: str,
        elements: list[dict[str, Any]],
    ) -> StateComparisonResult:
        graph_store = self._graph_store
        graph_id = self._graph_id
        if graph_store is None or not graph_id:
            return self._register_local(state_hash, elements)

        existing = await graph_store.get_semantic_profile(graph_id, state_hash)
        if existing is not None:
            return StateComparisonResult(
                state_hash,
                False,
                True,
                state_hash,
                1.0,
                {},
                "already_registered",
            )

        candidate = self._profiler.profile(state_hash, elements)
        if candidate.element_count == 0 or not np.any(candidate.pooled_vector):
            return await self._accept_persisted(candidate, "empty_or_unusable_profile")

        best_hash: str | None = None
        best_confidence = 0.0
        best_scores: dict[str, float] = {}
        seen = 0

        async for payload in graph_store.iter_semantic_profiles(
            graph_id,
            state_hash=state_hash,
            batch_size=self._batch_size,
            session_id=self._session_id or "",
            frontier_statuses=["exploring", "explored"],
        ):
            known = StateSemanticProfile.from_payload(payload)
            if known is None:
                continue
            seen += 1
            if seen > self._max_size:
                break
            confidence, scores = self._classifier.compare(candidate, known)
            if confidence > best_confidence:
                best_hash = known.state_hash
                best_confidence = confidence
                best_scores = scores

        confident_equivalence = (
            best_hash is not None
            and best_confidence >= self._threshold + self._uncertainty_margin
        )
        high_similarity_equivalence = (
            best_hash is not None
            and self._is_high_similarity_equivalence(best_scores)
        )
        if confident_equivalence or high_similarity_equivalence:
            reason = (
                "confident_equivalence"
                if confident_equivalence
                else "high_similarity_equivalence"
            )
            await graph_store.upsert_semantic_profile(
                graph_id,
                candidate.state_hash,
                candidate.to_payload(),
            )
            return StateComparisonResult(
                state_hash,
                False,
                True,
                best_hash,
                best_confidence,
                best_scores,
                reason,
            )

        reason = (
            "uncertain_comparison"
            if best_hash is not None
            and best_confidence >= self._threshold - self._uncertainty_margin
            else "novel_state"
        )
        return await self._accept_persisted(
            candidate,
            reason,
            best_hash,
            best_confidence,
            best_scores,
        )

    def _register_local(
        self,
        state_hash: str,
        elements: list[dict[str, Any]],
    ) -> StateComparisonResult:
        if state_hash in self._profiles:
            return StateComparisonResult(
                state_hash,
                False,
                True,
                state_hash,
                1.0,
                {},
                "already_registered",
            )

        candidate = self._profiler.profile(state_hash, elements)
        if candidate.element_count == 0 or not np.any(candidate.pooled_vector):
            return self._accept(candidate, "empty_or_unusable_profile")

        best_hash: str | None = None
        best_confidence = 0.0
        best_scores: dict[str, float] = {}
        for known_hash, known in self._profiles.items():
            confidence, scores = self._classifier.compare(candidate, known)
            if confidence > best_confidence:
                best_hash = known_hash
                best_confidence = confidence
                best_scores = scores

        confident_equivalence = (
            best_hash is not None
            and best_confidence >= self._threshold + self._uncertainty_margin
        )
        high_similarity_equivalence = (
            best_hash is not None
            and self._is_high_similarity_equivalence(best_scores)
        )
        if confident_equivalence or high_similarity_equivalence:
            reason = (
                "confident_equivalence"
                if confident_equivalence
                else "high_similarity_equivalence"
            )
            self._store_profile(candidate)
            return StateComparisonResult(
                state_hash,
                False,
                True,
                best_hash,
                best_confidence,
                best_scores,
                reason,
            )

        reason = (
            "uncertain_comparison"
            if best_hash is not None
            and best_confidence >= self._threshold - self._uncertainty_margin
            else "novel_state"
        )
        return self._accept(
            candidate,
            reason,
            best_hash,
            best_confidence,
            best_scores,
        )

    async def _accept_persisted(
        self,
        profile: StateSemanticProfile,
        reason: str,
        matched_hash: str | None = None,
        confidence: float = 0.0,
        scores: dict[str, float] | None = None,
    ) -> StateComparisonResult:
        graph_store = self._graph_store
        graph_id = self._graph_id
        if graph_store is None or not graph_id:
            return self._accept(profile, reason, matched_hash, confidence, scores)

        await graph_store.upsert_semantic_profile(
            graph_id,
            profile.state_hash,
            profile.to_payload(),
        )
        return StateComparisonResult(
            profile.state_hash,
            True,
            False,
            matched_hash,
            confidence,
            scores or {},
            reason,
        )

    def _is_high_similarity_equivalence(self, scores: dict[str, float]) -> bool:
        if not scores:
            return False
        if hasattr(self._classifier, "predicts_equivalent"):
            predicts_equivalent = getattr(self._classifier, "predicts_equivalent", None)
            if callable(predicts_equivalent) and not predicts_equivalent(scores):
                return False
        return all(
            scores.get(name, 0.0) >= minimum
            for name, minimum in HIGH_SIMILARITY_EQUIVALENCE_MINIMUMS.items()
        )

    def _accept(
        self,
        profile: StateSemanticProfile,
        reason: str,
        matched_hash: str | None = None,
        confidence: float = 0.0,
        scores: dict[str, float] | None = None,
    ) -> StateComparisonResult:
        self._store_profile(profile)

        return StateComparisonResult(
            profile.state_hash,
            True,
            False,
            matched_hash,
            confidence,
            scores or {},
            reason,
        )

    def _store_profile(self, profile: StateSemanticProfile) -> None:
        self._profiles[profile.state_hash] = profile
        self._profiles.move_to_end(profile.state_hash)
        while len(self._profiles) > self._max_size:
            self._profiles.popitem(last=False)


def pair_features(
    left: StateSemanticProfile,
    right: StateSemanticProfile,
) -> dict[str, float]:
    return {
        "element_similarity": _bidirectional_element_similarity(
            left.element_vectors,
            right.element_vectors,
        ),
        "pooled_similarity": _cosine(left.pooled_vector, right.pooled_vector),
        "topic_similarity": _cosine(
            left.topic_distribution,
            right.topic_distribution,
            empty_value=1.0,
        ),
        "structure_similarity": _cosine(
            left.structural_distribution,
            right.structural_distribution,
            empty_value=1.0,
        ),
        "count_similarity": (
            min(left.element_count, right.element_count)
            / max(left.element_count, right.element_count, 1)
        ),
    }


def _bidirectional_element_similarity(
    left: np.ndarray,
    right: np.ndarray,
) -> float:
    if not left.size or not right.size:
        return 0.0
    similarities = np.clip(left @ right.T, -1.0, 1.0)
    return float(
        (similarities.max(axis=1).mean() + similarities.max(axis=0).mean())
        / 2.0
    )


def _cosine(
    left: np.ndarray,
    right: np.ndarray,
    *,
    empty_value: float = 0.0,
) -> float:
    if not left.size or not right.size:
        return empty_value
    denominator = np.linalg.norm(left) * np.linalg.norm(right)
    if denominator == 0:
        return empty_value
    return float(np.clip(np.dot(left, right) / denominator, -1.0, 1.0))


def _normalize(values: np.ndarray) -> np.ndarray:
    total = float(values.sum())
    return values / total if total else values


def _plain_value(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return value

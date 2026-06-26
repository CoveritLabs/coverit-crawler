from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from src.crawler.semantic_engine.artifacts import (
    ModelArtifactLoader,
    save_model_bundle,
)
from src.crawler.semantic_engine.classifiers import (
    ManualBinaryClassifier,
    ManualSoftmaxClassifier,
    ManualTopicModel,
)
from src.crawler.semantic_engine.extractor import DOMFeatureExtractor
from src.crawler.semantic_engine.features import ManualElementFeatureEncoder
from src.crawler.semantic_engine.metrics import (
    binary_f1_score,
    classification_report_dict,
    macro_f1_score,
)
from src.crawler.semantic_engine.state import (
    PAIR_FEATURE_NAMES,
    StateProfiler,
    pair_features,
)
from src.crawler.semantic_engine.text_vectorizer import (
    ManualHashingTfidfEncoder,
    ManualTextFeatureCombiner,
    ManualTfidfEncoder,
)
from src.crawler.semantic_engine.topic import ManualTopicClassifier
from src.scripts.semantic_pipeline.datasets import (
    dataset_hash,
    read_state_snapshots,
)


def train_topic_model(
    train_path: Path,
    validation_path: Path,
    test_path: Path,
    output_path: Path,
    *,
    default_threshold: float,
) -> dict[str, Any]:
    train_texts, train_labels = _read_topic_rows(train_path)
    validation_texts, validation_labels = _read_topic_rows(validation_path)
    test_texts, test_labels = _read_topic_rows(test_path)
    if not train_texts:
        raise ValueError("Cannot train topic model without labeled training rows")

    vectorizer = ManualTextFeatureCombiner(
        [
            (
                "word",
                ManualTfidfEncoder(
                    ngram_range=(1, 2),
                    min_df=2,
                    max_features=20_000,
                    sublinear_tf=True,
                ),
            ),
            (
                "character",
                ManualTfidfEncoder(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    min_df=2,
                    max_features=30_000,
                    sublinear_tf=True,
                ),
            ),
        ]
    ).fit(train_texts)
    classifier = ManualSoftmaxClassifier(
        epochs=35,
        learning_rate=0.18,
        l2=1e-4,
        random_state=42,
    ).fit(
        vectorizer.transform_sparse(train_texts),
        train_labels,
        dimension=vectorizer.dimension,
    )
    model = ManualTopicModel(vectorizer, classifier)
    thresholds = _topic_thresholds(
        model,
        validation_texts,
        validation_labels,
        default_threshold,
    )
    predictions = model.predict(test_texts) if test_texts else []
    metrics = {
        "macro_f1": macro_f1_score(
            test_labels,
            predictions,
            labels=model.classes_,
        ),
        "classification_report": classification_report_dict(
            test_labels,
            predictions,
            labels=model.classes_,
        ),
    }
    save_model_bundle(
        output_path,
        kind="topic_classifier",
        model_version=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        dataset_hash=dataset_hash(
            [train_path, validation_path, test_path]
        ),
        payload={
            "model": model,
            "thresholds": thresholds,
            "default_threshold": default_threshold,
        },
        metrics=metrics,
    )
    return metrics


def train_state_model(
    snapshots_path: Path,
    pairs_path: Path,
    topic_artifact: Path,
    output_path: Path,
    *,
    components: int,
) -> dict[str, Any]:
    pairs = _read_state_pairs(pairs_path)
    if not pairs:
        raise ValueError("Cannot train state model without labeled state pairs")

    needed_state_ids = {
        state_id
        for left_id, right_id, _, _ in pairs
        for state_id in (left_id, right_id)
    }
    snapshots = {
        state_id: elements
        for state_id, elements in read_state_snapshots(snapshots_path).items()
        if state_id in needed_state_ids
    }
    topic_bundle = ModelArtifactLoader(topic_artifact.parent).load(
        topic_artifact.name,
        "topic_classifier",
    )
    topic_classifier = ManualTopicClassifier(
        topic_bundle.payload["model"],
        thresholds=topic_bundle.payload.get("thresholds"),
        default_threshold=float(
            topic_bundle.payload.get("default_threshold", 0.55)
        ),
    )
    extractor = DOMFeatureExtractor()
    corpus = [
        extractor.extract(element)
        for elements in snapshots.values()
        for element in elements
    ]
    corpus = [text for text in corpus if text]
    dimension = min(components, max(2, len(corpus) - 1))
    text_encoder = ManualHashingTfidfEncoder(
        n_features=dimension,
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
    ).fit(corpus)
    profiler = StateProfiler(
        ManualElementFeatureEncoder(
            text_encoder,
            topic_classifier=topic_classifier,
        ),
        topic_classifier,
    )
    profiles = {
        state_id: profiler.profile(state_id, elements)
        for state_id, elements in snapshots.items()
    }
    features = []
    labels = []
    splits = []
    for left_id, right_id, label, split in pairs:
        scores = pair_features(profiles[left_id], profiles[right_id])
        features.append([scores[name] for name in PAIR_FEATURE_NAMES])
        labels.append(label)
        splits.append(split)

    train_indices = [
        index for index, split in enumerate(splits) if split != "test"
    ]
    test_indices = [
        index for index, split in enumerate(splits) if split == "test"
    ]
    if not test_indices:
        test_indices = train_indices
    if not train_indices:
        train_indices = test_indices

    feature_matrix = np.asarray(features, dtype=float)
    label_vector = np.asarray(labels, dtype=int)
    classifier = ManualBinaryClassifier(
        epochs=700,
        learning_rate=0.08,
        l2=1e-4,
        random_state=42,
    ).fit(
        feature_matrix[train_indices],
        label_vector[train_indices],
    )
    predictions = classifier.predict(feature_matrix[test_indices])
    actual = label_vector[test_indices]
    metrics = {
        "macro_f1": macro_f1_score(actual.tolist(), predictions.tolist(), labels=[0, 1]),
        "classification_report": classification_report_dict(
            actual.tolist(),
            predictions.tolist(),
            labels=[0, 1],
        ),
    }
    save_model_bundle(
        output_path,
        kind="state_equivalence",
        model_version=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        dataset_hash=dataset_hash([snapshots_path, pairs_path]),
        payload={
            "text_encoder": text_encoder,
            "pair_classifier": classifier,
            "pair_feature_names": PAIR_FEATURE_NAMES,
        },
        metrics=metrics,
    )
    return metrics


def _read_topic_rows(path: Path) -> tuple[list[str], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row.get("flattened_text") and row.get("topic_label")
        ]
    return (
        [row["flattened_text"] for row in rows],
        [row["topic_label"] for row in rows],
    )


def _topic_thresholds(
    model: ManualTopicModel,
    texts: list[str],
    labels: list[str],
    default_threshold: float,
) -> dict[str, float]:
    if not texts:
        return {str(label): default_threshold for label in model.classes_}
    probabilities = model.predict_proba(texts)
    thresholds = {}
    for index, label in enumerate(model.classes_):
        actual = [int(item == label) for item in labels]
        best_threshold = default_threshold
        best_score = -1.0
        for threshold in np.linspace(0.35, 0.9, 23):
            predicted = [
                int(probability >= threshold)
                for probability in probabilities[:, index]
            ]
            score = binary_f1_score(actual, predicted)
            if score > best_score:
                best_score = float(score)
                best_threshold = float(threshold)
        thresholds[str(label)] = best_threshold
    return thresholds


def _read_state_pairs(
    path: Path,
) -> list[tuple[str, str, int, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        (
            row["left_state_id"],
            row["right_state_id"],
            int(row["equivalent"]),
            row["split"],
        )
        for row in rows
    ]

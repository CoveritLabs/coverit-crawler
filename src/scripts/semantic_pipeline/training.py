from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from sklearn.pipeline import FeatureUnion, Pipeline

from src.crawler.semantic_engine.artifacts import (
    ModelArtifactLoader,
    save_model_bundle,
)
from src.crawler.semantic_engine.extractor import DOMFeatureExtractor
from src.crawler.semantic_engine.features import SklearnElementFeatureEncoder
from src.crawler.semantic_engine.state import (
    PAIR_FEATURE_NAMES,
    StateProfiler,
    pair_features,
)
from src.crawler.semantic_engine.topic import SklearnTopicClassifier
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
) -> dict:
    train_texts, train_labels = _read_topic_rows(train_path)
    validation_texts, validation_labels = _read_topic_rows(validation_path)
    test_texts, test_labels = _read_topic_rows(test_path)
    pipeline = Pipeline(
        [
            (
                "features",
                FeatureUnion(
                    [
                        (
                            "word",
                            TfidfVectorizer(
                                ngram_range=(1, 2),
                                min_df=2,
                                max_features=20_000,
                                sublinear_tf=True,
                            ),
                        ),
                        (
                            "character",
                            TfidfVectorizer(
                                analyzer="char_wb",
                                ngram_range=(3, 5),
                                min_df=2,
                                max_features=30_000,
                                sublinear_tf=True,
                            ),
                        ),
                    ]
                ),
            ),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=2000,
                    random_state=42,
                ),
            ),
        ]
    )
    pipeline.fit(train_texts, train_labels)
    thresholds = _topic_thresholds(
        pipeline,
        validation_texts,
        validation_labels,
        default_threshold,
    )
    predictions = pipeline.predict(test_texts)
    metrics = {
        "macro_f1": float(
            f1_score(test_labels, predictions, average="macro")
        ),
        "classification_report": classification_report(
            test_labels,
            predictions,
            output_dict=True,
            zero_division=0,
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
            "pipeline": pipeline,
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
) -> dict:
    pairs = _read_state_pairs(pairs_path)
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
    topic_classifier = SklearnTopicClassifier(
        topic_bundle.payload["pipeline"],
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
    text_pipeline = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    ngram_range=(1, 2),
                    min_df=1,
                    sublinear_tf=True,
                ),
            ),
            (
                "svd",
                TruncatedSVD(
                    n_components=dimension,
                    random_state=42,
                ),
            ),
        ]
    )
    text_pipeline.fit(corpus)
    profiler = StateProfiler(
        SklearnElementFeatureEncoder(
            text_pipeline,
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
    classifier = LogisticRegression(
        class_weight="balanced",
        max_iter=1000,
        random_state=42,
    )
    classifier.fit(
        np.asarray(features)[train_indices],
        np.asarray(labels)[train_indices],
    )
    predictions = classifier.predict(np.asarray(features)[test_indices])
    actual = np.asarray(labels)[test_indices]
    metrics = {
        "macro_f1": float(f1_score(actual, predictions, average="macro")),
        "classification_report": classification_report(
            actual,
            predictions,
            output_dict=True,
            zero_division=0,
        ),
    }
    save_model_bundle(
        output_path,
        kind="state_equivalence",
        model_version=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        dataset_hash=dataset_hash([snapshots_path, pairs_path]),
        payload={
            "text_pipeline": text_pipeline,
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
    pipeline: Pipeline,
    texts: list[str],
    labels: list[str],
    default_threshold: float,
) -> dict[str, float]:
    if not texts:
        return {str(label): default_threshold for label in pipeline.classes_}
    probabilities = pipeline.predict_proba(texts)
    thresholds = {}
    for index, label in enumerate(pipeline.classes_):
        actual = np.asarray([item == label for item in labels], dtype=int)
        best_threshold = default_threshold
        best_score = -1.0
        for threshold in np.linspace(0.35, 0.9, 23):
            score = f1_score(
                actual,
                (probabilities[:, index] >= threshold).astype(int),
                zero_division=0,
            )
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

import csv
import json

import numpy as np

from src.crawler.semantic_engine.artifacts import ModelArtifactLoader, save_model_bundle
from src.crawler.semantic_engine.classifiers import (
    ManualSoftmaxClassifier,
    ManualTopicModel,
)
from src.crawler.semantic_engine.state import StateSemanticProfile, pair_features
from src.crawler.semantic_engine.text_vectorizer import (
    ManualTextFeatureCombiner,
    ManualTfidfEncoder,
)
from src.crawler.semantic_engine.topic import ManualTopicClassifier
from src.scripts.semantic_pipeline.training import train_state_model, train_topic_model


def test_manual_tfidf_builds_word_and_character_features():
    word = ManualTfidfEncoder(ngram_range=(1, 2), min_df=1)
    word.fit(["Email address", "Email field"])

    assert "email" in word.vocabulary_
    assert "email address" in word.vocabulary_
    assert np.isclose(np.linalg.norm(word.transform(["email address"])[0]), 1.0)

    character = ManualTfidfEncoder(
        analyzer="char_wb",
        ngram_range=(3, 3),
        min_df=1,
    )
    character.fit(["zip"])

    assert " zi" in character.vocabulary_
    assert "ip " in character.vocabulary_


def test_manual_topic_classifier_returns_thresholded_prediction():
    texts = [
        "email address field",
        "email login field",
        "password secret field",
        "password login field",
    ]
    labels = ["email", "email", "password", "password"]
    vectorizer = ManualTextFeatureCombiner(
        [
            ("word", ManualTfidfEncoder(ngram_range=(1, 2), min_df=1)),
            (
                "character",
                ManualTfidfEncoder(
                    analyzer="char_wb",
                    ngram_range=(3, 4),
                    min_df=1,
                ),
            ),
        ]
    ).fit(texts)
    classifier = ManualSoftmaxClassifier(
        epochs=80,
        learning_rate=0.25,
        random_state=7,
    ).fit(
        vectorizer.transform_sparse(texts),
        labels,
        dimension=vectorizer.dimension,
    )
    topic_model = ManualTopicModel(vectorizer, classifier)
    topic_classifier = ManualTopicClassifier(
        topic_model,
        thresholds={"email": 0.05, "password": 0.05},
    )

    prediction = topic_classifier.predict(
        {"tag": "input", "type": "email", "name": "email", "label": "Email"}
    )

    assert prediction.topic == "email"
    assert not prediction.abstained
    assert np.isclose(sum(prediction.probabilities.values()), 1.0)


def test_pair_features_score_identical_profiles_as_equivalent():
    left = StateSemanticProfile(
        "left",
        element_vectors=np.asarray([[1.0, 0.0], [0.0, 1.0]]),
        pooled_vector=np.asarray([0.70710678, 0.70710678]),
        topic_distribution=np.asarray([0.5, 0.5]),
        structural_distribution=np.asarray([1.0, 0.0]),
        element_count=2,
    )
    right = StateSemanticProfile(
        "right",
        element_vectors=np.asarray([[1.0, 0.0], [0.0, 1.0]]),
        pooled_vector=np.asarray([0.70710678, 0.70710678]),
        topic_distribution=np.asarray([0.5, 0.5]),
        structural_distribution=np.asarray([1.0, 0.0]),
        element_count=2,
    )

    scores = pair_features(left, right)

    assert scores["element_similarity"] == 1.0
    assert np.isclose(scores["pooled_similarity"], 1.0)
    assert np.isclose(scores["topic_similarity"], 1.0)
    assert scores["count_similarity"] == 1.0


def test_model_bundle_round_trips_with_joblib(tmp_path):
    artifact = tmp_path / "topic_model.joblib"

    save_model_bundle(
        artifact,
        kind="topic_classifier",
        model_version="test",
        dataset_hash="abc",
        payload={"value": 123},
    )
    bundle = ModelArtifactLoader(tmp_path).load(
        "topic_model.joblib",
        "topic_classifier",
    )

    assert bundle.payload == {"value": 123}
    assert bundle.model_version == "test"


def test_tiny_training_fixture_produces_manual_artifacts(tmp_path):
    topic_dir = tmp_path / "topic"
    topic_dir.mkdir()
    _write_topic_csv(
        topic_dir / "topic_train.csv",
        [
            ("email address field", "email"),
            ("email login field", "email"),
            ("password secret field", "password"),
            ("password login field", "password"),
        ],
    )
    _write_topic_csv(
        topic_dir / "topic_validation.csv",
        [
            ("email contact field", "email"),
            ("password account field", "password"),
        ],
    )
    _write_topic_csv(
        topic_dir / "topic_test.csv",
        [
            ("email form field", "email"),
            ("password form field", "password"),
        ],
    )
    topic_artifact = tmp_path / "topic_model.joblib"

    topic_metrics = train_topic_model(
        topic_dir / "topic_train.csv",
        topic_dir / "topic_validation.csv",
        topic_dir / "topic_test.csv",
        topic_artifact,
        default_threshold=0.55,
    )

    snapshots = tmp_path / "state_snapshots.jsonl"
    snapshots.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {
                    "state_id": "s1",
                    "elements": [
                        {"tag": "input", "type": "email", "name": "email"},
                        {"tag": "input", "type": "password", "name": "password"},
                    ],
                },
                {
                    "state_id": "s1-order",
                    "elements": [
                        {"tag": "input", "type": "password", "name": "password"},
                        {"tag": "input", "type": "email", "name": "email"},
                    ],
                },
                {
                    "state_id": "s2",
                    "elements": [
                        {"tag": "input", "type": "search", "name": "search"},
                    ],
                },
                {
                    "state_id": "s2-copy",
                    "elements": [
                        {"tag": "input", "type": "search", "name": "search"},
                    ],
                },
                {
                    "state_id": "s3",
                    "elements": [
                        {"tag": "textarea", "name": "message"},
                    ],
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    pairs = tmp_path / "state_pairs_labeled.csv"
    _write_state_pairs(
        pairs,
        [
            ("s1", "s1-order", 1, "train"),
            ("s2", "s3", 0, "train"),
            ("s1", "s2", 0, "test"),
            ("s2", "s2-copy", 1, "test"),
        ],
    )
    state_artifact = tmp_path / "state_equivalence.joblib"

    state_metrics = train_state_model(
        snapshots,
        pairs,
        topic_artifact,
        state_artifact,
        components=8,
    )

    assert topic_artifact.exists()
    assert state_artifact.exists()
    assert "macro_f1" in topic_metrics
    assert "macro_f1" in state_metrics
    topic_bundle = ModelArtifactLoader(tmp_path).load(
        "topic_model.joblib",
        "topic_classifier",
    )
    state_bundle = ModelArtifactLoader(tmp_path).load(
        "state_equivalence.joblib",
        "state_equivalence",
    )
    assert "model" in topic_bundle.payload
    assert "text_encoder" in state_bundle.payload
    assert "pair_classifier" in state_bundle.payload


def _write_topic_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["flattened_text", "topic_label"],
        )
        writer.writeheader()
        for text, label in rows:
            writer.writerow({"flattened_text": text, "topic_label": label})


def _write_state_pairs(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["left_state_id", "right_state_id", "equivalent", "split"],
        )
        writer.writeheader()
        for left, right, equivalent, split in rows:
            writer.writerow(
                {
                    "left_state_id": left,
                    "right_state_id": right,
                    "equivalent": equivalent,
                    "split": split,
                }
            )

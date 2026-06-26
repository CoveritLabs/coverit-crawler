from __future__ import annotations

from typing import Sequence

import numpy as np

from src.crawler.semantic_engine.vector_math import sigmoid, softmax, sparse_dot


class ManualTopicModel:
    def __init__(
        self,
        vectorizer: object,
        classifier: ManualSoftmaxClassifier,
    ):
        self.vectorizer = vectorizer
        self.classifier = classifier

    @property
    def classes_(self) -> tuple[str, ...]:
        return self.classifier.classes_

    def predict_proba(self, texts: list[str]) -> np.ndarray:
        rows = self.vectorizer.transform_sparse(texts)
        return self.classifier.predict_proba(rows)

    def predict(self, texts: list[str]) -> list[str]:
        rows = self.vectorizer.transform_sparse(texts)
        return self.classifier.predict(rows)


class ManualSoftmaxClassifier:
    def __init__(
        self,
        *,
        epochs: int = 35,
        learning_rate: float = 0.18,
        l2: float = 1e-4,
        random_state: int = 42,
    ):
        self.epochs = int(epochs)
        self.learning_rate = float(learning_rate)
        self.l2 = float(l2)
        self.random_state = int(random_state)
        self.classes_: tuple[str, ...] = ()
        self.weights_: np.ndarray = np.empty((0, 0), dtype=float)
        self.bias_: np.ndarray = np.empty(0, dtype=float)

    def fit(
        self,
        rows: list[dict[int, float]],
        labels: Sequence[str],
        *,
        dimension: int,
    ) -> ManualSoftmaxClassifier:
        if not rows:
            raise ValueError("Cannot train a topic model without rows")
        if len(rows) != len(labels):
            raise ValueError("Feature rows and labels must have the same length")

        self.classes_ = tuple(sorted(set(labels)))
        class_to_index = {label: index for index, label in enumerate(self.classes_)}
        y = np.asarray([class_to_index[label] for label in labels], dtype=int)
        class_count = len(self.classes_)
        self.weights_ = np.zeros((class_count, int(dimension)), dtype=float)
        self.bias_ = np.zeros(class_count, dtype=float)
        if class_count == 1:
            return self

        sample_weights = _balanced_sample_weights(y, class_count)
        order = np.arange(len(rows))
        randomizer = np.random.default_rng(self.random_state)
        for epoch in range(max(1, self.epochs)):
            randomizer.shuffle(order)
            rate = self.learning_rate / (1.0 + 0.04 * epoch)
            for row_index in order:
                row = rows[int(row_index)]
                target = int(y[row_index])
                logits = sparse_dot(self.weights_, row) + self.bias_
                probabilities = softmax(logits)
                delta = probabilities
                delta[target] -= 1.0
                delta *= sample_weights[row_index]

                self.bias_ -= rate * delta
                for feature_index, value in row.items():
                    if self.l2:
                        self.weights_[:, feature_index] *= 1.0 - rate * self.l2
                    self.weights_[:, feature_index] -= rate * delta * value
        return self

    def predict_proba(self, rows: list[dict[int, float]]) -> np.ndarray:
        if not self.classes_:
            raise ValueError("Classifier has not been trained")
        if len(self.classes_) == 1:
            return np.ones((len(rows), 1), dtype=float)

        output = np.zeros((len(rows), len(self.classes_)), dtype=float)
        for index, row in enumerate(rows):
            output[index] = softmax(sparse_dot(self.weights_, row) + self.bias_)
        return output

    def predict(self, rows: list[dict[int, float]]) -> list[str]:
        probabilities = self.predict_proba(rows)
        return [
            self.classes_[int(np.argmax(row))]
            for row in probabilities
        ]


class ManualBinaryClassifier:
    def __init__(
        self,
        *,
        epochs: int = 700,
        learning_rate: float = 0.08,
        l2: float = 1e-4,
        random_state: int = 42,
    ):
        self.epochs = int(epochs)
        self.learning_rate = float(learning_rate)
        self.l2 = float(l2)
        self.random_state = int(random_state)
        self.classes_ = np.asarray([0, 1], dtype=int)
        self.weights_: np.ndarray = np.empty(0, dtype=float)
        self.bias_: float = 0.0

    def fit(
        self,
        features: np.ndarray,
        labels: np.ndarray,
    ) -> ManualBinaryClassifier:
        x = np.asarray(features, dtype=float)
        y = np.asarray(labels, dtype=float)
        if x.ndim != 2 or x.shape[0] == 0:
            raise ValueError("Binary classifier needs a non-empty 2D feature matrix")
        if x.shape[0] != y.shape[0]:
            raise ValueError("Feature rows and labels must have the same length")

        self.weights_ = np.zeros(x.shape[1], dtype=float)
        self.bias_ = 0.0
        sample_weights = _binary_sample_weights(y)
        order = np.arange(x.shape[0])
        randomizer = np.random.default_rng(self.random_state)
        for epoch in range(max(1, self.epochs)):
            randomizer.shuffle(order)
            rate = self.learning_rate / (1.0 + 0.02 * epoch)
            for row_index in order:
                row = x[int(row_index)]
                probability = float(sigmoid(np.asarray([np.dot(row, self.weights_) + self.bias_]))[0])
                delta = (probability - y[row_index]) * sample_weights[row_index]
                self.weights_ *= 1.0 - rate * self.l2
                self.weights_ -= rate * delta * row
                self.bias_ -= rate * delta
        return self

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        x = np.asarray(features, dtype=float)
        if x.ndim == 1:
            x = x.reshape(1, -1)
        positive = sigmoid(x @ self.weights_ + self.bias_)
        return np.column_stack([1.0 - positive, positive])

    def predict(self, features: np.ndarray) -> np.ndarray:
        return (self.predict_proba(features)[:, 1] >= 0.5).astype(int)


def _balanced_sample_weights(
    labels: np.ndarray,
    class_count: int,
) -> np.ndarray:
    counts = np.bincount(labels, minlength=class_count)
    total = len(labels)
    weights = np.ones(total, dtype=float)
    for class_index, count in enumerate(counts):
        if count:
            weights[labels == class_index] = total / (class_count * count)
    return weights


def _binary_sample_weights(labels: np.ndarray) -> np.ndarray:
    positives = int(labels.sum())
    negatives = int(len(labels) - positives)
    weights = np.ones(len(labels), dtype=float)
    if positives:
        weights[labels == 1] = len(labels) / (2.0 * positives)
    if negatives:
        weights[labels == 0] = len(labels) / (2.0 * negatives)
    return weights

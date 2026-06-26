from __future__ import annotations

import numpy as np


def clip(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return float(min(max(value, lower), upper))


def cosine(
    left: np.ndarray,
    right: np.ndarray,
    *,
    empty_value: float = 0.0,
) -> float:
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    if left.size == 0 or right.size == 0:
        return empty_value
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator == 0.0:
        return empty_value
    return clip(float(np.dot(left, right) / denominator))


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    values = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(values))
    return values / norm if norm else values


def l2_normalize_rows(matrix: np.ndarray) -> np.ndarray:
    values = np.asarray(matrix, dtype=float)
    if values.size == 0:
        return values
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return values / norms


def normalize_distribution(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    total = float(values.sum())
    return values / total if total else values


def sigmoid(logits: np.ndarray) -> np.ndarray:
    values = np.asarray(logits, dtype=float)
    positive = values >= 0
    negative = ~positive
    output = np.empty_like(values, dtype=float)
    output[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exp_values = np.exp(values[negative])
    output[negative] = exp_values / (1.0 + exp_values)
    return output


def softmax(logits: np.ndarray) -> np.ndarray:
    values = np.asarray(logits, dtype=float)
    if values.ndim == 1:
        shifted = values - np.max(values)
        exp_values = np.exp(shifted)
        total = float(exp_values.sum())
        return exp_values / total if total else exp_values

    shifted = values - np.max(values, axis=1, keepdims=True)
    exp_values = np.exp(shifted)
    totals = exp_values.sum(axis=1, keepdims=True)
    totals[totals == 0.0] = 1.0
    return exp_values / totals


def sparse_dot(weights: np.ndarray, row: dict[int, float]) -> np.ndarray:
    scores = np.zeros(weights.shape[0], dtype=float)
    for index, value in row.items():
        scores += weights[:, index] * value
    return scores

from __future__ import annotations

from collections import Counter
from typing import Any, Sequence


def binary_f1_score(
    actual: Sequence[int | bool],
    predicted: Sequence[int | bool],
) -> float:
    true_positive = sum(1 for left, right in zip(actual, predicted, strict=True) if left and right)
    false_positive = sum(1 for left, right in zip(actual, predicted, strict=True) if not left and right)
    false_negative = sum(1 for left, right in zip(actual, predicted, strict=True) if left and not right)
    denominator = (2 * true_positive) + false_positive + false_negative
    return (2 * true_positive / denominator) if denominator else 0.0


def macro_f1_score(
    actual: Sequence[Any],
    predicted: Sequence[Any],
    *,
    labels: Sequence[Any] | None = None,
) -> float:
    selected_labels = list(labels or sorted(set(actual) | set(predicted)))
    if not selected_labels:
        return 0.0
    scores = [
        _label_scores(actual, predicted, label)["f1-score"]
        for label in selected_labels
    ]
    return float(sum(scores) / len(scores)) if scores else 0.0


def classification_report_dict(
    actual: Sequence[Any],
    predicted: Sequence[Any],
    *,
    labels: Sequence[Any] | None = None,
) -> dict[str, Any]:
    selected_labels = list(labels or sorted(set(actual) | set(predicted)))
    report = {
        str(label): _label_scores(actual, predicted, label)
        for label in selected_labels
    }
    support = Counter(actual)
    total = len(actual)
    accuracy = (
        sum(1 for left, right in zip(actual, predicted, strict=True) if left == right)
        / total
        if total
        else 0.0
    )
    macro = _average_report(report.values(), selected_labels)
    weighted = _weighted_average_report(report, selected_labels, support, total)
    report["accuracy"] = float(accuracy)
    report["macro avg"] = macro
    report["weighted avg"] = weighted
    return report


def _label_scores(
    actual: Sequence[Any],
    predicted: Sequence[Any],
    label: Any,
) -> dict[str, float]:
    true_positive = sum(
        1
        for left, right in zip(actual, predicted, strict=True)
        if left == label and right == label
    )
    false_positive = sum(
        1
        for left, right in zip(actual, predicted, strict=True)
        if left != label and right == label
    )
    false_negative = sum(
        1
        for left, right in zip(actual, predicted, strict=True)
        if left == label and right != label
    )
    support = sum(1 for item in actual if item == label)
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1-score": float(f1),
        "support": float(support),
    }


def _average_report(
    reports: Sequence[dict[str, float]],
    labels: Sequence[Any],
) -> dict[str, float]:
    if not labels:
        return {"precision": 0.0, "recall": 0.0, "f1-score": 0.0, "support": 0.0}
    rows = list(reports)
    return {
        metric: float(sum(row[metric] for row in rows) / len(labels))
        for metric in ("precision", "recall", "f1-score")
    } | {"support": float(sum(row["support"] for row in rows))}


def _weighted_average_report(
    report: dict[str, dict[str, float]],
    labels: Sequence[Any],
    support: Counter[Any],
    total: int,
) -> dict[str, float]:
    if not total:
        return {"precision": 0.0, "recall": 0.0, "f1-score": 0.0, "support": 0.0}
    output = {}
    for metric in ("precision", "recall", "f1-score"):
        output[metric] = float(
            sum(
                report[str(label)][metric] * support[label]
                for label in labels
            )
            / total
        )
    output["support"] = float(total)
    return output

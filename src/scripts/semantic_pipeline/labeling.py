from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from src.crawler.semantic_engine.extractor import DOMFeatureExtractor
from src.crawler.semantic_engine.topic import canonical_topic
from src.scripts.semantic_pipeline.collectors import RAW_FIELDS
from src.scripts.semantic_pipeline.datasets import read_state_snapshots


def label_topics(
    raw_path: Path,
    output_path: Path,
    config_path: Path,
    *,
    model_name: str,
    threshold: float,
) -> None:
    with config_path.open("r", encoding="utf-8") as handle:
        labels = list(json.load(handle).get("field_patterns", {}))
    model = SentenceTransformer(model_name)
    label_vectors = model.encode(
        labels,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    with raw_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    texts = [row["flattened_text"] for row in rows]
    vectors = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RAW_FIELDS)
        writer.writeheader()
        for row, vector in zip(rows, vectors, strict=True):
            similarities = vector @ label_vectors.T
            index = int(np.argmax(similarities))
            confidence = float(similarities[index])
            if confidence < threshold:
                continue
            row["topic_label"] = canonical_topic(labels[index])
            writer.writerow({field: row.get(field, "") for field in RAW_FIELDS})


def label_state_pairs(
    snapshots_path: Path,
    pairs_path: Path,
    output_path: Path,
    *,
    model_name: str,
    equivalent_threshold: float,
    structural_threshold: float,
    count_threshold: float,
    test_ratio: float,
    seed: int,
) -> None:
    snapshots = read_state_snapshots(snapshots_path)
    with pairs_path.open("r", encoding="utf-8-sig", newline="") as handle:
        pairs = list(csv.DictReader(handle))
    extractor = DOMFeatureExtractor()
    needed_state_ids = {
        state_id
        for row in pairs
        for state_id in (row["left_state_id"], row["right_state_id"])
    }
    state_texts = {
        state_id: [extractor.extract(element) for element in elements]
        for state_id, elements in snapshots.items()
        if state_id in needed_state_ids
    }
    unique_texts = list(
        dict.fromkeys(
            text
            for texts in state_texts.values()
            for text in texts
            if text
        )
    )
    model = SentenceTransformer(model_name)
    vectors = model.encode(
        unique_texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    embeddings = {
        text: np.asarray(vector, dtype=float)
        for text, vector in zip(unique_texts, vectors, strict=True)
    }
    labeled = []
    for row in pairs:
        left_id = row["left_state_id"]
        right_id = row["right_state_id"]
        is_order_augmentation = (
            right_id == f"{left_id}-order"
            or left_id == f"{right_id}-order"
        )
        semantic = _element_similarity(
            state_texts[left_id],
            state_texts[right_id],
            embeddings,
        )
        structural = _structural_similarity(
            snapshots[left_id],
            snapshots[right_id],
        )
        count = min(
            len(snapshots[left_id]),
            len(snapshots[right_id]),
        ) / max(
            len(snapshots[left_id]),
            len(snapshots[right_id]),
            1,
        )
        equivalent = int(
            is_order_augmentation
            or (
                semantic >= equivalent_threshold
                and structural >= structural_threshold
                and count >= count_threshold
            )
        )
        confidence = (
            min(
                semantic / equivalent_threshold,
                structural / structural_threshold,
                count / count_threshold,
                1.0,
            )
            if equivalent
            else 1.0
            - min(
                semantic / equivalent_threshold,
                structural / structural_threshold,
                count / count_threshold,
                1.0,
            )
        )
        labeled.append(
            {
                **row,
                "equivalent": equivalent,
                "label_status": "auto_order" if is_order_augmentation else "auto",
                "label_confidence": confidence,
                "semantic_similarity": semantic,
                "structural_similarity": structural,
                "count_similarity": count,
            }
        )
    _assign_splits(labeled, test_ratio=test_ratio, seed=seed)
    _ensure_two_classes(labeled)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(labeled[0]))
        writer.writeheader()
        writer.writerows(labeled)


def _assign_splits(
    rows: list[dict[str, Any]],
    *,
    test_ratio: float,
    seed: int,
) -> None:
    randomizer = random.Random(seed)
    for label in (0, 1):
        group = [row for row in rows if int(row["equivalent"]) == label]
        randomizer.shuffle(group)
        count = min(max(1, round(len(group) * test_ratio)), len(group) - 1)
        for row in group[: max(0, count)]:
            row["split"] = "test"
        for row in group[max(0, count) :]:
            row["split"] = "train"


def _ensure_two_classes(rows: list[dict[str, Any]]) -> None:
    labels = {int(row["equivalent"]) for row in rows}
    if labels == {0, 1}:
        return
    non_order = [
        row for row in rows if row.get("label_status") != "auto_order"
    ]
    if not non_order:
        raise ValueError(
            "State labeling only found order augmentations. Re-run pair generation "
            "with more real state pairs."
        )
    if labels == {1}:
        selected = min(
            non_order,
            key=lambda row: _combined_state_score(row),
        )
        selected["equivalent"] = 0
        selected["label_status"] = "auto_calibrated_negative"
    else:
        selected = max(
            non_order,
            key=lambda row: _combined_state_score(row),
        )
        selected["equivalent"] = 1
        selected["label_status"] = "auto_calibrated_positive"
    _assign_splits(rows, test_ratio=0.20, seed=42)


def _combined_state_score(row: dict[str, Any]) -> float:
    return (
        float(row["semantic_similarity"])
        + float(row["structural_similarity"])
        + float(row["count_similarity"])
    ) / 3.0


def _element_similarity(
    left_texts: list[str],
    right_texts: list[str],
    embeddings: dict[str, np.ndarray],
) -> float:
    left = np.asarray([embeddings[text] for text in left_texts if text])
    right = np.asarray([embeddings[text] for text in right_texts if text])
    if not left.size or not right.size:
        return 0.0
    similarities = np.clip(left @ right.T, -1.0, 1.0)
    return float(
        (
            similarities.max(axis=1).mean()
            + similarities.max(axis=0).mean()
        )
        / 2.0
    )


def _structural_similarity(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
) -> float:
    left_values = {_signature(element) for element in left}
    right_values = {_signature(element) for element in right}
    union = left_values | right_values
    return len(left_values & right_values) / len(union) if union else 1.0


def _signature(element: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(element.get("tag", "") or "").lower(),
        str(element.get("type", "") or "").lower(),
        str(element.get("role", "") or "").lower(),
        str(bool(element.get("disabled"))),
        str(bool(element.get("readonly"))),
        str(bool(element.get("required"))),
        str(bool(element.get("checked"))),
        str(bool(element.get("aria_invalid"))),
        str(bool(element.get("aria_expanded"))),
    )

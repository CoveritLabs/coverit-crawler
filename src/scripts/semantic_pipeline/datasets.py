from __future__ import annotations

import csv
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from src.crawler.semantic_engine.extractor import (
    DOMFeatureExtractor,
    normalize_semantic_text,
)
from src.crawler.semantic_engine.topic import canonical_topic

VALUE_BEARING_TAGS = {"input", "select", "textarea"}
EXCLUDED_INPUT_TYPES = {
    "button",
    "checkbox",
    "file",
    "hidden",
    "image",
    "radio",
    "reset",
    "submit",
}
DATASET_FIELDS = (
    "flattened_text",
    "topic_label",
    "tag",
    "type",
    "id",
    "name",
    "text",
    "value",
    "placeholder",
    "label",
    "aria_label",
    "role",
    "provenance",
    "review_status",
)


@dataclass(frozen=True)
class PreparedDatasets:
    all_rows: list[dict[str, str]]
    train_rows: list[dict[str, str]]
    validation_rows: list[dict[str, str]]
    test_rows: list[dict[str, str]]


def prepare_topic_dataset(
    raw_path: str | Path,
    labeled_path: str | Path,
    *,
    seed: int = 42,
) -> PreparedDatasets:
    raw_rows = _read_csv(raw_path)
    labeled_rows = _read_csv(labeled_path)
    raw_by_text: dict[str, dict[str, str]] = {}
    for row in raw_rows:
        key = normalize_semantic_text(row.get("flattened_text"))
        if key and key not in raw_by_text:
            raw_by_text[key] = row

    extractor = DOMFeatureExtractor()
    prepared_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for labeled in labeled_rows:
        normalized = normalize_semantic_text(labeled.get("flattened_text"))
        raw = raw_by_text.get(normalized)
        if raw is None or not _is_value_bearing(raw):
            continue

        topic = canonical_topic(labeled.get("topic_label", ""))
        if not topic:
            continue

        combined = {**raw, **labeled}
        feature_text = extractor.extract(combined)
        if not feature_text:
            continue

        prepared = {
            field: str(combined.get(field, "") or "") for field in DATASET_FIELDS
        }
        prepared["flattened_text"] = feature_text
        prepared["topic_label"] = topic
        prepared["provenance"] = "raw.csv+labeled.csv"
        prepared["review_status"] = "proposed"
        prepared_by_key[(feature_text, topic)] = prepared

    groups: dict[str, list[dict[str, str]]] = {}
    for row in prepared_by_key.values():
        groups.setdefault(row["flattened_text"], []).append(row)

    train_keys, validation_keys, test_keys = _stratified_group_split(
        groups,
        seed,
    )
    return PreparedDatasets(
        all_rows=list(prepared_by_key.values()),
        train_rows=_rows_for_keys(groups, train_keys),
        validation_rows=_rows_for_keys(groups, validation_keys),
        test_rows=_rows_for_keys(groups, test_keys),
    )


def write_prepared_datasets(
    datasets: PreparedDatasets,
    output_dir: str | Path,
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / "topic_all.csv", datasets.all_rows)
    _write_csv(output / "topic_train.csv", datasets.train_rows)
    _write_csv(output / "topic_validation.csv", datasets.validation_rows)
    _write_csv(output / "topic_test.csv", datasets.test_rows)


def read_state_snapshots(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    snapshots: dict[str, list[dict[str, Any]]] = {}
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            state_id = str(row.get("state_id", "")).strip()
            elements = row.get("elements")
            if not state_id or not isinstance(elements, list):
                raise ValueError(f"Invalid state snapshot on line {line_number}")
            snapshots[state_id] = elements
    return snapshots


def prepare_state_pairs(
    snapshots_path: str | Path,
    output_path: str | Path,
    *,
    max_pairs: int,
) -> None:
    snapshots = read_state_snapshots(snapshots_path)
    metadata = _read_snapshot_metadata(snapshots_path)
    extractor = DOMFeatureExtractor()
    tokens = {
        state_id: set(
            normalize_semantic_text(
                " ".join(extractor.extract(item) for item in elements)
            ).split()
        )
        for state_id, elements in snapshots.items()
    }
    guaranteed = []
    candidate_ids = set()
    state_ids = sorted(snapshots)
    for index, left_id in enumerate(state_ids):
        augmented = metadata.get(left_id, {}).get("augmentation_of")
        if augmented and augmented in snapshots:
            guaranteed.append((1.0, str(augmented), left_id))
        if index + 1 < len(state_ids):
            candidate_ids.add((left_id, state_ids[index + 1]))
        if index + 10 < len(state_ids):
            candidate_ids.add((left_id, state_ids[index + 10]))
    randomizer = random.Random(42)
    sample_target = max_pairs * 50
    while len(candidate_ids) < min(sample_target, len(state_ids) * 20):
        left_id, right_id = randomizer.sample(state_ids, 2)
        if left_id == right_id:
            continue
        candidate_ids.add(tuple(sorted((left_id, right_id))))
    candidates = [
        (_jaccard(tokens[left_id], tokens[right_id]), left_id, right_id)
        for left_id, right_id in candidate_ids
        if not left_id.endswith("-order")
        and not right_id.endswith("-order")
    ]
    guaranteed.sort(reverse=True)
    candidates.sort(reverse=True)
    positive_limit = min(len(guaranteed), max(1, max_pairs // 3))
    remaining = max(0, max_pairs - positive_limit)
    high_limit = remaining // 2
    low_limit = remaining - high_limit
    selected = (
        guaranteed[:positive_limit]
        + candidates[:high_limit]
        + list(reversed(candidates[-low_limit:] if low_limit else []))
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "left_state_id",
                "right_state_id",
                "equivalent",
                "split",
                "label_status",
                "label_confidence",
                "semantic_similarity",
                "structural_similarity",
                "count_similarity",
            ]
        )
        for score, left_id, right_id in selected:
            writer.writerow(
                [left_id, right_id, "", "", "", "", score, "", ""]
            )


def dataset_hash(paths: Iterable[str | Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(item) for item in paths):
        digest.update(path.name.encode())
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _read_snapshot_metadata(path: str | Path) -> dict[str, dict[str, Any]]:
    metadata = {}
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                metadata[str(row["state_id"])] = row
    return metadata


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DATASET_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _is_value_bearing(row: dict[str, str]) -> bool:
    tag = str(row.get("tag", "") or "").lower()
    input_type = str(row.get("type", "") or "").lower()
    return tag in VALUE_BEARING_TAGS and input_type not in EXCLUDED_INPUT_TYPES


def _stratified_group_split(
    groups: dict[str, list[dict[str, str]]],
    seed: int,
) -> tuple[set[str], set[str], set[str]]:
    keys_by_label: dict[str, list[str]] = {}
    for key, rows in groups.items():
        label = rows[0]["topic_label"]
        keys_by_label.setdefault(label, []).append(key)

    train: set[str] = set()
    validation: set[str] = set()
    test: set[str] = set()
    randomizer = random.Random(seed)
    for label in sorted(keys_by_label):
        keys = sorted(keys_by_label[label])
        randomizer.shuffle(keys)
        if len(keys) < 3:
            train.update(keys)
            continue

        validation_count = max(1, round(len(keys) * 0.15))
        test_count = max(1, round(len(keys) * 0.20))
        train_count = max(1, len(keys) - validation_count - test_count)
        train.update(keys[:train_count])
        validation.update(keys[train_count : train_count + validation_count])
        test.update(keys[train_count + validation_count :])

    return train, validation, test


def _rows_for_keys(
    groups: dict[str, list[dict[str, str]]],
    keys: set[str],
) -> list[dict[str, str]]:
    return [row for key in keys for row in groups[key]]

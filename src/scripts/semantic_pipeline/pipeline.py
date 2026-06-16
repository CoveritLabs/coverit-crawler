from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.scripts.semantic_pipeline.collectors import SemanticDataCollector
from src.scripts.semantic_pipeline.datasets import (
    prepare_state_pairs,
    prepare_topic_dataset,
    write_prepared_datasets,
)
from src.scripts.semantic_pipeline.labeling import (
    label_state_pairs,
    label_topics,
)
from src.scripts.semantic_pipeline.training import (
    train_state_model,
    train_topic_model,
)
from src.scripts.semantic_pipeline.websites import TARGET_URLS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineSettings:
    workspace: Path
    artifacts: Path
    input_config: Path
    max_websites: int
    max_pages_per_domain: int
    max_actions_per_page: int
    max_pairs: int
    timeout_ms: int
    headless: bool
    labeling_model: str
    reuse_collected: bool = False


async def run_pipeline(settings: PipelineSettings) -> None:
    if not settings.reuse_collected:
        _clean(settings.workspace)
    raw = settings.workspace / "raw.csv"
    labeled = settings.workspace / "labeled.csv"
    snapshots = settings.workspace / "state_snapshots.jsonl"
    pairs = settings.workspace / "state_pairs.csv"
    labeled_pairs = settings.workspace / "state_pairs_labeled.csv"
    topic_data = settings.workspace / "topic"
    staged_artifacts = settings.workspace / "artifacts"
    topic_artifact = staged_artifacts / "topic_model.joblib"
    state_artifact = staged_artifacts / "state_equivalence.joblib"
    urls = (
        TARGET_URLS[: settings.max_websites]
        if settings.max_websites
        else TARGET_URLS
    )

    if settings.reuse_collected:
        _require_existing(raw, snapshots)
    else:
        await SemanticDataCollector(
            raw,
            snapshots,
            max_pages_per_domain=settings.max_pages_per_domain,
            max_actions_per_page=settings.max_actions_per_page,
            timeout_ms=settings.timeout_ms,
            headless=settings.headless,
        ).collect(urls)

    if settings.reuse_collected and labeled.exists() and topic_artifact.exists():
        topic_metrics = {"macro_f1": 0.0}
    else:
        label_topics(
            raw,
            labeled,
            settings.input_config,
            model_name=settings.labeling_model,
            threshold=0.45,
        )
        prepared = prepare_topic_dataset(raw, labeled)
        write_prepared_datasets(prepared, topic_data)
        topic_metrics = train_topic_model(
            topic_data / "topic_train.csv",
            topic_data / "topic_validation.csv",
            topic_data / "topic_test.csv",
            topic_artifact,
            default_threshold=0.55,
        )

    prepare_state_pairs(
        snapshots,
        pairs,
        max_pairs=settings.max_pairs,
    )
    label_state_pairs(
        snapshots,
        pairs,
        labeled_pairs,
        model_name=settings.labeling_model,
        equivalent_threshold=0.82,
        structural_threshold=0.90,
        count_threshold=0.85,
        test_ratio=0.20,
        seed=42,
    )
    state_metrics = train_state_model(
        snapshots,
        labeled_pairs,
        topic_artifact,
        state_artifact,
        components=100,
    )
    _publish(staged_artifacts, settings.artifacts)
    logger.info(
        "Completed topic_f1=%.3f state_f1=%.3f",
        topic_metrics["macro_f1"],
        state_metrics["macro_f1"],
    )


def _clean(workspace: Path) -> None:
    resolved = workspace.resolve()
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def _require_existing(*paths: Path) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Cannot reuse collected data; missing " + ", ".join(missing)
        )


def _publish(staged: Path, destination: Path) -> None:
    resolved = destination.resolve()
    if resolved.exists():
        shutil.rmtree(resolved)
    shutil.copytree(staged, resolved)

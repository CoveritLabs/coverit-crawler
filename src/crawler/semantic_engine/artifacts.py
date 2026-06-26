from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

import joblib

ARTIFACT_SCHEMA_VERSION = 1


class ArtifactError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelBundle:
    kind: str
    model_version: str
    dataset_hash: str
    payload: dict[str, Any]
    metrics: dict[str, Any]


class ModelArtifactLoader:
    def __init__(self, artifact_dir: str | Path):
        self._artifact_dir = Path(artifact_dir).expanduser().resolve()

    @property
    def artifact_dir(self) -> Path:
        return self._artifact_dir

    def load(self, filename: str, expected_kind: str) -> ModelBundle:
        path = self._artifact_dir / filename
        if not path.is_file():
            raise ArtifactError(f"Model artifact not found: {path}")

        try:
            raw = joblib.load(path)
        except Exception as exc:
            raise ArtifactError(f"Could not load model artifact: {path}") from exc

        if not isinstance(raw, dict):
            raise ArtifactError(f"Invalid artifact payload: {path}")
        if raw.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
            raise ArtifactError(f"Incompatible artifact schema: {path}")
        if raw.get("kind") != expected_kind:
            raise ArtifactError(f"Expected {expected_kind} artifact: {path}")
        if not isinstance(raw.get("payload"), dict):
            raise ArtifactError(f"Artifact payload is missing: {path}")

        return ModelBundle(
            kind=expected_kind,
            model_version=str(raw.get("model_version", "")),
            dataset_hash=str(raw.get("dataset_hash", "")),
            payload=raw["payload"],
            metrics=dict(raw.get("metrics") or {}),
        )


_MODEL_BUNDLE_CACHE: dict[tuple[str, str, str], ModelBundle] = {}
_MODEL_BUNDLE_CACHE_LOCK = Lock()


def load_cached_model_bundle(
    artifact_dir: str | Path,
    filename: str,
    expected_kind: str,
) -> ModelBundle:
    artifact_path = Path(artifact_dir).expanduser().resolve()
    cache_key = (str(artifact_path), filename, expected_kind)

    with _MODEL_BUNDLE_CACHE_LOCK:
        cached = _MODEL_BUNDLE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        bundle = ModelArtifactLoader(artifact_path).load(filename, expected_kind)
        _MODEL_BUNDLE_CACHE[cache_key] = bundle
        return bundle


def clear_model_bundle_cache() -> None:
    with _MODEL_BUNDLE_CACHE_LOCK:
        _MODEL_BUNDLE_CACHE.clear()


def save_model_bundle(
    path: str | Path,
    *,
    kind: str,
    model_version: str,
    dataset_hash: str,
    payload: dict[str, Any],
    metrics: dict[str, Any] | None = None,
) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite immutable artifact: {output}")

    joblib.dump(
        {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "kind": kind,
            "model_version": model_version,
            "dataset_hash": dataset_hash,
            "payload": payload,
            "metrics": metrics or {},
        },
        output,
    )

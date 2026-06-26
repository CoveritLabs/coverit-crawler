from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = ["CrawlerWorker"]

_EXPORTS: dict[str, tuple[str, str]] = {
    "CrawlerWorker": ("src.workers.crawler_worker", "CrawlerWorker"),
}


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    value = getattr(import_module(module_name), attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(_EXPORTS.keys()))


if TYPE_CHECKING:
    from src.workers.crawler_worker import CrawlerWorker

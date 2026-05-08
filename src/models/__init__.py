from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = ["AbstractState", "AbstractTransition", "CrawlAction", "CrawlJob"]

_EXPORTS: dict[str, tuple[str, str]] = {
	"AbstractState": ("src.models.graph", "AbstractState"),
	"AbstractTransition": ("src.models.graph", "AbstractTransition"),
	"CrawlAction": ("src.models.graph", "CrawlAction"),
	"CrawlJob": ("src.models.crawl_job", "CrawlJob"),
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
	from src.models.crawl_job import CrawlJob
	from src.models.graph import AbstractState, AbstractTransition, CrawlAction


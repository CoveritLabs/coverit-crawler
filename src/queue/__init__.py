from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
	"CrawlStreamConfig",
	"ack_and_delete",
	"cancel_key",
	"clear_cancel",
	"crawl_stream_config",
	"ensure_consumer_group",
	"is_cancelled",
	"parse_session_id",
]

_EXPORTS: dict[str, tuple[str, str]] = {
	"CrawlStreamConfig": ("src.queue.crawl_stream", "CrawlStreamConfig"),
	"ack_and_delete": ("src.queue.crawl_stream", "ack_and_delete"),
	"cancel_key": ("src.queue.crawl_stream", "cancel_key"),
	"clear_cancel": ("src.queue.crawl_stream", "clear_cancel"),
	"crawl_stream_config": ("src.queue.crawl_stream", "crawl_stream_config"),
	"ensure_consumer_group": ("src.queue.crawl_stream", "ensure_consumer_group"),
	"is_cancelled": ("src.queue.crawl_stream", "is_cancelled"),
	"parse_session_id": ("src.queue.crawl_stream", "parse_session_id"),
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
	from src.queue.crawl_stream import (
		CrawlStreamConfig,
		ack_and_delete,
		cancel_key,
		clear_cancel,
		crawl_stream_config,
		ensure_consumer_group,
		is_cancelled,
		parse_session_id,
	)

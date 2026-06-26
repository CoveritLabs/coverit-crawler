from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "ActionRepeatLimiter",
    "ActionType",
    "CrawlSession",
    "EventExecutor",
    "HtmlTag",
    "InputType",
    "InputValueResolver",
    "RiskClassifier",
    "StateReplayInfo",
    "StateReplayer",
]

_EXPORTS: dict[str, tuple[str, str]] = {
    "ActionRepeatLimiter": ("src.crawler.action_limits", "ActionRepeatLimiter"),
    "ActionType": ("src.crawler.enums", "ActionType"),
    "CrawlSession": ("src.crawler.session", "CrawlSession"),
    "EventExecutor": ("src.crawler.executor", "EventExecutor"),
    "HtmlTag": ("src.crawler.enums", "HtmlTag"),
    "InputType": ("src.crawler.enums", "InputType"),
    "InputValueResolver": ("src.crawler.input_resolver", "InputValueResolver"),
    "RiskClassifier": ("src.crawler.risk", "RiskClassifier"),
    "StateReplayInfo": ("src.crawler.replay", "StateReplayInfo"),
    "StateReplayer": ("src.crawler.replay", "StateReplayer"),
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
    from src.crawler.action_limits import ActionRepeatLimiter
    from src.crawler.enums import ActionType, HtmlTag, InputType
    from src.crawler.executor import EventExecutor
    from src.crawler.input_resolver import InputValueResolver
    from src.crawler.replay import StateReplayer, StateReplayInfo
    from src.crawler.risk import RiskClassifier
    from src.crawler.session import CrawlSession

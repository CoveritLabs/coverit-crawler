from __future__ import annotations

from dataclasses import dataclass

from src.models import AbstractState, CrawlAction


@dataclass
class DeferredWorkItem:
    source_state: AbstractState
    actions: list[CrawlAction]
    element: dict | None = None

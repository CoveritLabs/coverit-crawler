from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

@dataclass
class AbstractState:
    """Represents an abstract state in the application state graph."""

    state_hash: str = ""
    url: str = ""
    title: str = ""
    dom_snapshot: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.state_hash)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AbstractState):
            return False
        return self.state_hash == other.state_hash


@dataclass
class AbstractTransition:
    """Represents a transition between states."""

    session_id: str = ""
    transition_id: str = ""
    source_state_hash: str = ""
    target_state_hash: str = ""
    action_type: str = ""
    action_description: str = ""
    locator_id: str = ""
    locator_value: str = ""
    action_value: str = ""
    action_fingerprint: str = ""


@dataclass
class CrawlAction:
    """Represents an executable action."""

    action_id: str = field(default_factory=lambda: str(uuid4()))
    action_type: str = ""
    selector: str = ""
    value: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

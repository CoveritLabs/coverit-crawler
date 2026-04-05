from dataclasses import dataclass, field
from typing import Any, Dict
from uuid import uuid4


@dataclass
class AbstractState:
    """Represents an abstract state in the application state graph."""

    state_id: str = ""
    state_hash: str = "" 
    url: str = ""
    title: str = ""
    dom_snapshot: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __hash__(self):
        return hash(self.state_hash)

    def __eq__(self, other):
        if not isinstance(other, AbstractState):
            return False
        return self.state_hash == other.state_hash


@dataclass
class AbstractTransition:
    """Represents a transition between states."""

    transition_id: str = ""
    source_state_id: str = ""
    target_state_id: str = ""
    action_type: str = ""  # click, type, navigate, etc.
    action_description: str = ""
    locator_id: str = ""
    locator_value: str = ""


@dataclass
class CrawlAction:
    """Represents an executable action."""

    action_id: str = field(default_factory=lambda: str(uuid4()))
    action_type: str = ""  # click, type, navigate, submit
    selector: str = ""
    value: str = ""  # for type actions
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

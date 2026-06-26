from typing import List

from src.models import CrawlAction
from src.utils import stable_json_dumps


def sequence_description(actions: List[CrawlAction]) -> str:
    if not actions:
        return ""

    if len(actions) == 1:
        return _action_description_with_value(actions[0])

    parts = []
    for action in actions:
        description = _action_description_with_value(action)
        if description:
            parts.append(description)

    return f"Sequence ({len(actions)}): " + " -> ".join(parts)


def sequence_value_for_graph(actions: List[CrawlAction]) -> str:
    payload = [
        {
            "t": action.action_type,
            "s": action.selector,
            "v": _saved_value(action),
            "d": _action_description_with_value(action),
        }
        for action in actions
    ]
    return stable_json_dumps(payload)


def sequence_digest(actions: List[CrawlAction]) -> str:
    import hashlib

    payload = [
        {"t": action.action_type, "s": action.selector, "v": action.value}
        for action in actions
    ]
    raw = stable_json_dumps(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _saved_value(action: CrawlAction) -> str:
    if action.action_type in ("navigate", "select", "press", "type"):
        return str(action.value or "")

    return ""


def _action_description_with_value(action: CrawlAction) -> str:
    description = str(action.description or action.action_type).strip()
    value = _saved_value(action)

    if not value:
        return description

    return f"{description} value={value}"

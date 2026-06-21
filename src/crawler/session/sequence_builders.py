from typing import List

from src.models import CrawlAction
from src.utils import stable_json_dumps


def sequence_description(actions: List[CrawlAction]) -> str:
    if not actions:
        return ""

    if len(actions) == 1:
        return actions[0].description

    parts = []
    for a in actions[:6]:
        d = str(a.description or a.action_type).strip()
        if d:
            parts.append(d)

    suffix = ""
    if len(actions) > 6:
        suffix = f" … (+{len(actions) - 6} more)"

    return f"Sequence ({len(actions)}): " + " -> ".join(parts) + suffix


def sequence_value_for_graph(actions: List[CrawlAction]) -> str:
    payload = [
        {
            "t": a.action_type,
            "s": a.selector,
            "v": _safe_value(a),
            "d": a.description,
        }
        for a in actions
    ]
    return stable_json_dumps(payload)


def sequence_digest(actions: List[CrawlAction]) -> str:
    import hashlib

    payload = [{"t": a.action_type, "s": a.selector, "v": a.value} for a in actions]
    raw = stable_json_dumps(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_value(action: CrawlAction) -> str:
    if action.action_type in ("navigate", "select", "press","type"):
        return str(action.value or "")

    return ""

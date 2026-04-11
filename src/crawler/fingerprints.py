import hashlib
import json
from typing import Any, Dict

from ..models.graph import CrawlAction


def _stable_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def action_attempt_fingerprint(source_state_hash: str, action: CrawlAction) -> str:
    payload = {
        "action_type": action.action_type,
        "selector": action.selector,
        "value": action.value,
        "metadata": action.metadata or {},
    }
    raw = f"{source_state_hash}|{_stable_dumps(payload)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def transition_fingerprint(
    *,
    session_id: str,
    source_state_hash: str,
    target_state_hash: str,
    action: CrawlAction,
) -> str:
    payload: Dict[str, Any] = {
        "session_id": session_id,
        "source": source_state_hash,
        "target": target_state_hash,
        "action_type": action.action_type,
        "selector": action.selector,
        "value": action.value,
        "metadata": action.metadata or {},
    }
    raw = _stable_dumps(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def best_effort_action_value(action: CrawlAction) -> str:
    if action.action_type in ("type", "select", "navigate", "press"):
        return str(action.value or "")
    return ""
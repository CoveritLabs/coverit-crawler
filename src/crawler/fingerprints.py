import hashlib
from typing import Any

from src.models import CrawlAction
from src.utils import stable_json_dumps


def action_attempt_fingerprint(source_state_hash: str, action: CrawlAction) -> str:
    payload = {
        "action_type": action.action_type,
        "selector": action.selector,
        "value": action.value,
        "metadata": action.metadata or {},
    }
    raw = f"{source_state_hash}|{stable_json_dumps(payload)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def action_key_fingerprint(action: CrawlAction) -> str:
    meta = action.metadata or {}
    payload = {
        "action_type": action.action_type,
        "selector": action.selector,
        "value": action.value,
        "sequence_digest": meta.get("sequence_digest"),
    }
    raw = stable_json_dumps(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def transition_fingerprint(
    *,
    session_id: str,
    source_state_hash: str,
    target_state_hash: str,
    action: CrawlAction,
) -> str:
    payload: dict[str, Any] = {
        "session_id": session_id,
        "source": source_state_hash,
        "target": target_state_hash,
        "action_type": action.action_type,
        "selector": action.selector,
        "value": action.value,
        "metadata": action.metadata or {},
    }
    raw = stable_json_dumps(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def best_effort_action_value(action: CrawlAction) -> str:
    if action.action_type in ("type", "select", "navigate", "press"):
        return str(action.value or "")
    return ""

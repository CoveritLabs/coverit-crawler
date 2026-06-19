import hashlib
from typing import Any

from src.models import CrawlAction
from src.utils import stable_json_dumps


def _stable_frame_key(frame: Any) -> dict[str, str]:
    if not isinstance(frame, dict):
        return {}
    return {
        "name": str(frame.get("name") or ""),
        "id": str(frame.get("id") or ""),
        "src": str(frame.get("src") or ""),
        "url": str(frame.get("url") or ""),
    }


def action_identity_payload(action: CrawlAction) -> dict[str, Any]:
    meta = action.metadata or {}
    element_key = str(meta.get("element_key") or "")

    stable_meta: dict[str, Any] = {
        "element_key": element_key,
        "form_id": meta.get("form_id"),
        "form_method": meta.get("form_method"),
        "form_action": meta.get("form_action"),
        "field": meta.get("field"),
        "type": meta.get("type"),
        "option": meta.get("option"),
        "sequence_digest": meta.get("sequence_digest"),
        "sequence_len": meta.get("sequence_len"),
    }
    frame = _stable_frame_key(meta.get("frame"))
    if frame:
        stable_meta["frame"] = frame

    stable_meta = {key: value for key, value in stable_meta.items() if value not in (None, "", {})}

    return {
        "action_type": action.action_type,
        "selector": "" if element_key else action.selector,
        "value": action.value,
        "metadata": stable_meta,
    }


def action_attempt_fingerprint(source_state_hash: str, action: CrawlAction) -> str:
    payload = action_identity_payload(action)
    raw = f"{source_state_hash}|{stable_json_dumps(payload)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def action_key_fingerprint(action: CrawlAction) -> str:
    payload = action_identity_payload(action)
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
        "action": action_identity_payload(action),
    }
    raw = stable_json_dumps(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def best_effort_action_value(action: CrawlAction) -> str:
    if action.action_type in ("type", "select", "navigate", "press"):
        return str(action.value or "")
    return ""

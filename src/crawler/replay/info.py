from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.models import CrawlAction
from src.utils import stable_json_dumps


@dataclass
class StateReplayInfo:
    checkpoint_url: str
    checkpoint_state_hash: str = ""
    checkpoint_kind: str = "url_change"
    actions: list[CrawlAction] = field(default_factory=list)
    storage_state: Any | None = None
    fallback_checkpoint_url: str | None = None
    fallback_checkpoint_state_hash: str | None = None
    fallback_actions: list[CrawlAction] = field(default_factory=list)
    fallback_storage_state: Any | None = None

    @staticmethod
    def action_to_dict(action: CrawlAction) -> dict[str, Any]:
        return {
            "id": action.action_id,
            "type": action.action_type,
            "selector": action.selector,
            "value": action.value,
            "description": action.description,
            "metadata": action.metadata,
        }

    @staticmethod
    def action_from_dict(raw: dict[str, Any]) -> CrawlAction:
        return CrawlAction(
            action_id=str(raw.get("id") or ""),
            action_type=str(raw.get("type") or ""),
            selector=str(raw.get("selector") or ""),
            value=str(raw.get("value") or ""),
            description=str(raw.get("description") or ""),
            metadata=dict(raw.get("metadata") or {}),
        )

    @classmethod
    def from_neo4j_record(cls, record: dict[str, Any] | None) -> StateReplayInfo | None:
        if not record or not record.get("checkpoint_url"):
            return None

        return cls(
            checkpoint_url=str(record.get("checkpoint_url") or ""),
            checkpoint_state_hash=str(record.get("checkpoint_state_hash") or ""),
            checkpoint_kind=str(record.get("checkpoint_kind") or "url_change"),
            actions=cls._actions_from_json(record.get("replay_actions_json")),
            storage_state=cls._json_value(record.get("checkpoint_storage_state_json")),
            fallback_checkpoint_url=record.get("fallback_checkpoint_url"),
            fallback_checkpoint_state_hash=record.get("fallback_checkpoint_state_hash"),
            fallback_actions=cls._actions_from_json(record.get("fallback_actions_json")),
            fallback_storage_state=cls._json_value(record.get("fallback_storage_state_json")),
        )

    @staticmethod
    def _json_value(value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except Exception:
            return value

    @classmethod
    def _actions_from_json(cls, value: Any) -> list[CrawlAction]:
        if not value:
            return []
        try:
            raw = json.loads(value) if isinstance(value, str) else value
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        return [cls.action_from_dict(item) for item in raw if isinstance(item, dict)]

    def to_neo4j_props(self, *, state_hash: str) -> dict[str, Any]:
        props: dict[str, Any] = {
            "replay_recipe_version": 1,
            "checkpoint_url": self.checkpoint_url,
            "checkpoint_state_hash": self.checkpoint_state_hash,
            "checkpoint_kind": self.checkpoint_kind,
            "replay_actions_json": stable_json_dumps([self.action_to_dict(a) for a in self.actions]),
        }

        if self.fallback_checkpoint_url:
            props["fallback_checkpoint_url"] = self.fallback_checkpoint_url
        if self.fallback_checkpoint_state_hash:
            props["fallback_checkpoint_state_hash"] = self.fallback_checkpoint_state_hash
        if self.fallback_actions:
            props["fallback_actions_json"] = stable_json_dumps([self.action_to_dict(a) for a in self.fallback_actions])
        if self.fallback_storage_state is not None:
            props["fallback_storage_state_json"] = self.fallback_storage_state

        props["is_checkpoint"] = bool(state_hash and self.checkpoint_state_hash == state_hash)
        return props

    def score_for_state(self, state_hash: str) -> tuple[int, int, int, int, str]:
        is_self_checkpoint = bool(state_hash and self.checkpoint_state_hash == state_hash)
        kind_rank = 0 if self.checkpoint_kind == "initial" else 1
        checkpoint_url = str(self.checkpoint_url or "")
        return (
            0 if is_self_checkpoint else 1,
            len(self.actions),
            len(self.fallback_actions),
            kind_rank,
            checkpoint_url,
        )

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.utils import stable_json_dumps
from src.models import CrawlAction


@dataclass
class StateReplayInfo:
    checkpoint_url: str
    checkpoint_state_hash: str = ""
    checkpoint_kind: str = "url_change"
    actions: list[CrawlAction] = field(default_factory=list)
    fallback_checkpoint_url: str | None = None
    fallback_checkpoint_state_hash: str | None = None
    fallback_actions: list[CrawlAction] = field(default_factory=list)

    def to_neo4j_props(self, *, state_hash: str) -> dict[str, Any]:
        def action_to_dict(action: CrawlAction) -> dict[str, Any]:
            return {
                "id": action.action_id,
                "type": action.action_type,
                "selector": action.selector,
                "value": action.value,
                "description": action.description,
                "metadata": action.metadata,
            }

        props: dict[str, Any] = {
            "replay_recipe_version": 1,
            "checkpoint_url": self.checkpoint_url,
            "checkpoint_state_hash": self.checkpoint_state_hash,
            "checkpoint_kind": self.checkpoint_kind,
            "replay_actions_json": stable_json_dumps([action_to_dict(a) for a in self.actions]),
        }

        if self.fallback_checkpoint_url:
            props["fallback_checkpoint_url"] = self.fallback_checkpoint_url
        if self.fallback_checkpoint_state_hash:
            props["fallback_checkpoint_state_hash"] = self.fallback_checkpoint_state_hash
        if self.fallback_actions:
            props["fallback_actions_json"] = stable_json_dumps([action_to_dict(a) for a in self.fallback_actions])

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

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class ActionRepeatLimiter:
    max_repeats_per_scope: int
    _counts: Dict[str, Dict[str, int]]

    def __init__(self, *, max_repeats_per_scope: int):
        self.max_repeats_per_scope = max(0, int(max_repeats_per_scope))
        self._counts = {}

    def can_run(self, *, scope: str, action_key: str) -> bool:
        if self.max_repeats_per_scope <= 0:
            return False
        return self._counts.get(scope, {}).get(action_key, 0) < self.max_repeats_per_scope

    def record(self, *, scope: str, action_key: str) -> None:
        scope_counts = self._counts.setdefault(scope, {})
        scope_counts[action_key] = scope_counts.get(action_key, 0) + 1

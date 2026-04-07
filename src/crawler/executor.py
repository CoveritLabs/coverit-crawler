from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..browser.engine import BrowserEngine
from ..models.graph import AbstractTransition, CrawlAction


@dataclass
class StateReplayInfo:
    checkpoint_url: str
    actions: List[CrawlAction] = field(default_factory=list)


class EventExecutor:
    def __init__(self, browser: BrowserEngine):
        self._browser = browser
        self._transition_log: List[AbstractTransition] = []

    async def execute_action(self, action: CrawlAction) -> None:
        try:
            if action.action_type == "click":
                await self._browser.click(action.selector)
            elif action.action_type == "type":
                await self._browser.type_text(action.selector, action.value)
            elif action.action_type == "navigate":
                await self._browser.navigate(action.value)
        except Exception as e:
            raise RuntimeError(f"Failed to execute {action.action_type} on {action.selector}: {e}") from e

    def log_transition(self, transition: AbstractTransition) -> None:
        self._transition_log.append(transition)

    def get_transition_log(self) -> List[AbstractTransition]:
        return self._transition_log


class StateReplayer:
    def __init__(self, browser: BrowserEngine, executor: EventExecutor):
        self._browser = browser
        self._executor = executor
        self._replay_map: Dict[str, StateReplayInfo] = {}

    def register(self, state_id: str, info: StateReplayInfo) -> None:
        self._replay_map[state_id] = info

    def get_info(self, state_id: str) -> Optional[StateReplayInfo]:
        return self._replay_map.get(state_id)

    async def replay_to(self, state_id: str) -> None:
        info = self._replay_map.get(state_id)
        if not info:
            return
        
        await self._browser.navigate(info.checkpoint_url)
        for action in info.actions:
            await self._executor.execute_action(action)
            await self._browser.wait_for_navigation()
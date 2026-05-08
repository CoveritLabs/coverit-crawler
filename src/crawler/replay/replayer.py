from __future__ import annotations

from src.browser import BrowserEngine
from src.config import Config, config
from src.crawler.replay.info import StateReplayInfo
from src.models import CrawlAction


class StateReplayer:
    def __init__(self, browser: BrowserEngine, executor, settings: Config = config):
        self._browser = browser
        self._executor = executor
        self._settings = settings
        self._replay_map: dict[str, StateReplayInfo] = {}

    def register(self, state_hash: str, info: StateReplayInfo) -> bool:
        existing = self._replay_map.get(state_hash)
        if existing is None:
            self._replay_map[state_hash] = info
            return True

        if info.score_for_state(state_hash) < existing.score_for_state(state_hash):
            self._replay_map[state_hash] = info
            return True

        return False

    def get_info(self, state_hash: str) -> StateReplayInfo | None:
        return self._replay_map.get(state_hash)

    async def replay_to(self, state_hash: str) -> bool:
        info = self._replay_map.get(state_hash)
        if not info:
            return False

        async def attempt(checkpoint_url: str, actions: list[CrawlAction]) -> bool:
            last_error: Exception | None = None
            for _ in range(self._settings.REPLAY_RETRY_COUNT + 1):
                try:
                    await self._browser.navigate(checkpoint_url)
                    await self._browser.wait_for_settle()
                    for action in actions:
                        await self._executor.execute_action(action)
                    await self._browser.wait_for_settle()
                    current_hash = await self._browser.get_state_hash()
                    if current_hash == state_hash:
                        return True
                except Exception as e:
                    last_error = e
            if last_error:
                raise last_error
            return False

        try:
            if await attempt(info.checkpoint_url, info.actions):
                return True
        except Exception:
            pass

        if info.fallback_checkpoint_url:
            return await attempt(info.fallback_checkpoint_url, info.fallback_actions)
        return False

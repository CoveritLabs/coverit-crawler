from __future__ import annotations

from typing import Any

from src.browser import BrowserEngine
from src.config import Config, config
from src.crawler.replay.info import StateReplayInfo
from src.models import CrawlAction


class StateReplayer:
    def __init__(self, browser: BrowserEngine, executor, graph_store, session_id: str, settings: Config = config):
        self._browser = browser
        self._executor = executor
        self._graph_store = graph_store
        self._session_id = session_id
        self._settings = settings

    async def register(self, state_hash: str, info: StateReplayInfo) -> bool:
        return await self._graph_store.upsert_replay_info_if_better(
            self._session_id,
            state_hash,
            info.to_neo4j_props(state_hash=state_hash),
            list(info.score_for_state(state_hash)),
        )

    async def get_info(self, state_hash: str) -> StateReplayInfo | None:
        raw = await self._graph_store.get_replay_info(self._session_id, state_hash)
        return StateReplayInfo.from_neo4j_record(raw)

    async def replay_to(self, state_hash: str) -> bool:
        info = await self.get_info(state_hash)
        if not info:
            return False

        async def attempt(checkpoint_url: str, actions: list[CrawlAction], storage_state: Any | None = None) -> bool:
            last_error: Exception | None = None
            for _ in range(self._settings.REPLAY_RETRY_COUNT + 1):
                try:
                    if storage_state is not None:
                        await self._browser.reset_context_from_storage_state(storage_state)
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
            if await attempt(info.checkpoint_url, info.actions, info.storage_state):
                return True
        except Exception:
            pass

        if info.fallback_checkpoint_url:
            return await attempt(info.fallback_checkpoint_url, info.fallback_actions, info.fallback_storage_state)
        return False

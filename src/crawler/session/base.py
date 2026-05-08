from __future__ import annotations

import asyncio
import logging
from collections import deque
from uuid import uuid4

from src.browser import BrowserEngine
from src import Config, config
from src.crawler.action_limits import ActionRepeatLimiter
from src.crawler.executor import EventExecutor
from src.crawler.replay import StateReplayInfo, StateReplayer
from src.crawler.risk import RiskClassifier
from src.crawler.session.types import DeferredWorkItem
from src.models import AbstractState, AbstractTransition

logger = logging.getLogger(__name__)


class CrawlSessionBase:
    def __init__(
        self,
        base_url: str,
        graph_builder,
        config_path: str | None = None,
        session_id: str | None = None,
        headless: bool | None = None,
        max_states: int | None = None,
        max_transitions: int | None = None,
        timeout_ms: int | None = None,
        input_defaults: dict | None = None,
        *,
        browser: BrowserEngine | None = None,
        settings: Config = config,
        risk_classifier: RiskClassifier | None = None,
        run_permission: asyncio.Event | None = None,
    ):
        self._settings = settings
        self._run_permission = run_permission
        self.base_url = base_url
        self.graph_builder = graph_builder
        self.headless = settings.HEADLESS if headless is None else headless
        self.config_path = config_path
        self._input_defaults = input_defaults
        self.session_id = session_id or str(uuid4())

        self.discovered_states: set[str] = set()
        self.discovery_queue: deque[AbstractState] = deque()
        self._deferred_work: deque[DeferredWorkItem] = deque()
        self._tried_actions_by_state: dict[str, set[str]] = {}
        self._seen_transition_ids: set[str] = set()
        self._risk = risk_classifier or RiskClassifier.from_settings(settings)
        self._login_attempts = 0
        self._action_repeat_limiter = ActionRepeatLimiter(
            max_repeats_per_scope=int(getattr(settings, "MAX_ACTION_REPEATS_PER_URL", 2))
        )

        self.browser = browser or BrowserEngine(
            headless=self.headless,
            timeout_ms=timeout_ms,
            settings=settings,
        )
        self.executor: EventExecutor | None = None
        self.replayer: StateReplayer | None = None
        self._max_states: int = int(max_states if max_states is not None else getattr(settings, "MAX_STATES", 1000))
        self._max_transitions: int = int(
            max_transitions if max_transitions is not None else getattr(settings, "MAX_TRANSITIONS", 5000)
        )
        self._state_count: int = 0
        self._transition_count: int = 0

    @property
    def state_count(self) -> int:
        return self._state_count

    @property
    def transition_count(self) -> int:
        return self._transition_count

    async def _wait_permission(self) -> None:
        if self._run_permission is not None:
            await self._run_permission.wait()

    async def initialize(self) -> None:
        await self.browser.start()
        self.executor = EventExecutor(
            self.browser,
            config_path=self.config_path,
            input_defaults=self._input_defaults,
        )
        self.replayer = StateReplayer(self.browser, self.executor, self._settings)
        logger.info("Crawl session initialized")

    async def cleanup(self) -> None:
        await self.browser.stop()
        logger.info("Crawl session completed")

    async def add_to_queue(self, state: AbstractState) -> None:
        if state.state_hash in self.discovered_states:
            return
        await self._wait_permission()
        self._state_count += 1
        self.discovered_states.add(state.state_hash)
        self.discovery_queue.append(state)
        await self.graph_builder.add_state(self.session_id, state)

    def get_next_state(self) -> AbstractState | None:
        return self.discovery_queue.popleft() if self.discovery_queue else None

    async def add_transition(self, transition: AbstractTransition) -> None:
        if transition.transition_id in self._seen_transition_ids:
            return
        await self._wait_permission()
        self._seen_transition_ids.add(transition.transition_id)
        self._transition_count += 1
        await self.graph_builder.add_transition(transition)
        if self.executor:
            self.executor.log_transition(transition)

    @property
    def is_complete(self) -> bool:
        return not self.discovery_queue

    def _within_limits(self) -> bool:
        return self._state_count < self._max_states and self._transition_count < self._max_transitions

    async def run_crawl(self) -> None:
        try:
            await self.initialize()
            await self._seed_initial_state()

            while self._within_limits():
                await self._wait_permission()
                if not self.is_complete:
                    current = self.get_next_state()
                    if current:
                        logger.info(
                            f"Exploring state {current.state_hash} "
                            f"({self._state_count}/{self._max_states} states, "
                            f"{self._transition_count}/{self._max_transitions} transitions)"
                        )
                        await self._explore_state(current)
                    continue

                if self._settings.DEFER_DESTRUCTIVE_ACTIONS and self._deferred_work:
                    item = self._deferred_work.popleft()
                    await self._run_deferred_item(item)
                    continue

                break

            logger.info(f"Crawl complete. States: {self._state_count}, Transitions: {self._transition_count}")
        except Exception as e:
            logger.error(f"Crawl failed: {e}", exc_info=True)
            raise
        finally:
            await self.cleanup()

    async def _seed_initial_state(self) -> None:
        await self._wait_permission()
        await self.browser.navigate(self.base_url)
        await self.browser.wait_for_settle()

        await self._attempt_login_if_needed()
        await self.browser.wait_for_settle()

        initial_state = await self.browser.capture_state()
        if not self.replayer:
            return
        await self.add_to_queue(initial_state)

        info = StateReplayInfo(
            checkpoint_url=initial_state.url,
            checkpoint_state_hash=initial_state.state_hash,
            checkpoint_kind="initial",
        )
        updated = self.replayer.register(initial_state.state_hash, info)
        if updated:
            await self._persist_replay_artifacts(
                state_hash=initial_state.state_hash,
                info=info,
                persist_storage_state=True,
            )
        logger.info(f"Initial state: {initial_state.state_hash} at {initial_state.url}")

    async def _attempt_login_if_needed(self) -> None:
        if self._login_attempts >= 2:
            return
        if not self.executor:
            return

        await self._wait_permission()

        forms = await self.browser.get_forms()
        login_form = self._select_login_form(forms)
        if not login_form:
            return

        self._login_attempts += 1
        actions = self.executor.plan_form_submission(login_form)
        if not actions:
            return

        for action in actions:
            await self._wait_permission()
            await self.executor.execute_action(action)

    def _select_login_form(self, forms: list[dict]) -> dict | None:
        for form in forms:
            fields = form.get("fields", [])
            if any(str(f.get("type", "")).lower() == "password" for f in fields):
                submit = form.get("submit")
                if submit and submit.get("selector"):
                    return form
        return None

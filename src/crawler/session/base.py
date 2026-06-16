from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from uuid import uuid4

from src import Config, config
from src.browser import BrowserEngine
from src.crawler.action_limits import ActionRepeatLimiter
from src.crawler.executor import EventExecutor
from src.crawler.replay import StateReplayer, StateReplayInfo
from src.crawler.risk import RiskClassifier
from src.crawler.semantic_engine import SemanticEngine
from src.crawler.session.types import DeferredWorkItem
from src.models import AbstractState, AbstractTransition, CrawlAction

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
        self._action_repeat_limiter = ActionRepeatLimiter(max_repeats_per_scope=int(getattr(settings, "MAX_ACTION_REPEATS_PER_URL", 2)))

        self.browser = browser or BrowserEngine(
            headless=self.headless,
            timeout_ms=timeout_ms,
            settings=settings,
        )
        self.executor: EventExecutor | None = None
        self.replayer: StateReplayer | None = None
        self._semantic_engine: SemanticEngine | None = None
        self._max_states: int = int(max_states if max_states is not None else getattr(settings, "MAX_STATES", 1000))
        self._max_transitions: int = int(max_transitions if max_transitions is not None else getattr(settings, "MAX_TRANSITIONS", 5000))
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
        input_config = self._resolved_input_config()
        field_patterns = input_config.get("field_patterns", {})

        self._semantic_engine = SemanticEngine(
            input_defaults=field_patterns,
            artifact_dir=self._settings.SEMANTIC_ARTIFACT_DIR,
            enabled=self._settings.USE_SEMANTIC_DIVERSITY,
            similarity_threshold=self._settings.SEMANTIC_DIVERSITY_THRESHOLD,
            uncertainty_margin=self._settings.SEMANTIC_UNCERTAINTY_MARGIN,
            max_bank_size=self._settings.SEMANTIC_MAX_BANK_SIZE,
        )
        self.executor = EventExecutor(
            self.browser,
            config_path=self.config_path,
            input_defaults=input_config,
            semantic_engine=self._semantic_engine,
        )
        self.replayer = StateReplayer(self.browser, self.executor, self._settings)

        logger.info("Crawl session initialized")

    def _resolved_input_config(self) -> dict:
        if isinstance(self._input_defaults, dict):
            if "field_patterns" in self._input_defaults or "type_fallbacks" in self._input_defaults:
                return self._input_defaults
            return {"field_patterns": self._input_defaults, "type_fallbacks": {}}

        if self.config_path:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                return json.load(handle)

        return {"field_patterns": {}, "type_fallbacks": {}}

    async def cleanup(self) -> None:
        await self.browser.stop()
        logger.info("Crawl session completed")

    async def add_to_queue(self, state: AbstractState, *, enqueue: bool = True) -> None:
        if state.state_hash in self.discovered_states:
            return
        await self._wait_permission()
        self._state_count += 1
        self.discovered_states.add(state.state_hash)
        if enqueue:
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

        initial_state = await self.browser.capture_state()
        if not self.replayer:
            return

        login_actions = await self._plan_login_actions()

        if self._semantic_engine:
            initial_elements = await self.browser.get_interactable_elements()
            self._semantic_engine.register_state(initial_state.state_hash, initial_elements)

        await self.add_to_queue(initial_state, enqueue=not bool(login_actions))

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

        if login_actions:
            reached = await self._execute_action_sequence(initial_state, info, login_actions)
            if not reached:
                self.discovery_queue.append(initial_state)

    async def _plan_login_actions(self) -> list[CrawlAction] | None:
        if self._login_attempts >= 2:
            return None
        if not self.executor:
            return None

        await self._wait_permission()

        forms = await self.browser.get_forms()
        login_form = self._select_login_form(forms)
        if not login_form:
            return None

        actions = self.executor.plan_form_submission(login_form)
        if not actions:
            return None

        self._login_attempts += 1
        return actions

    def _select_login_form(self, forms: list[dict]) -> dict | None:
        for form in forms:
            fields = form.get("fields", [])
            if any(str(f.get("type", "")).lower() == "password" for f in fields):
                submit = form.get("submit")
                if submit and submit.get("selector"):
                    return form
        return None

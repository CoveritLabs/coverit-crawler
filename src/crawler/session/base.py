from __future__ import annotations

import asyncio
import logging
import time
from uuid import uuid4

from src import Config, config
from src.browser import BrowserEngine, BrowserRuntime
from src.crawler.executor import EventExecutor
from src.crawler.input_defaults import resolve_input_defaults
from src.crawler.replay import StateReplayer, StateReplayInfo
from src.crawler.risk import RiskClassifier
from src.crawler.semantic_engine import SemanticEngine
from src.models import AbstractState, AbstractTransition, CrawlAction

logger = logging.getLogger(__name__)


class CrawlSessionBase:
    def __init__(
        self,
        base_url: str,
        graph_builder,
        config_path: str | None = None,
        graph_id: str | None = None,
        session_id: str | None = None,
        headless: bool | None = None,
        max_states: int | None = None,
        max_transitions: int | None = None,
        timeout_ms: int | None = None,
        input_defaults: dict | None = None,
        *,
        browser: BrowserEngine | None = None,
        browser_runtime: BrowserRuntime | None = None,
        settings: Config = config,
        risk_classifier: RiskClassifier | None = None,
        run_permission: asyncio.Event | None = None,
        stop_requested: asyncio.Event | None = None,
        slice_deadline_monotonic: float | None = None,
        initial_state_count: int = 0,
        initial_transition_count: int = 0,
    ):
        self._settings = settings
        self._run_permission = run_permission
        self._stop_requested = stop_requested
        self._slice_deadline_monotonic = slice_deadline_monotonic
        self.base_url = base_url
        self.graph_builder = graph_builder
        self.headless = settings.HEADLESS if headless is None else headless
        self.config_path = config_path
        self._input_defaults = input_defaults
        self.graph_id = graph_id or str(uuid4())
        self.session_id = session_id or str(uuid4())

        self._risk = risk_classifier or RiskClassifier.from_settings(settings)
        self._login_attempts = 0

        self.browser = browser or BrowserEngine(
            headless=self.headless,
            timeout_ms=timeout_ms,
            settings=settings,
            runtime=browser_runtime,
        )
        self.executor: EventExecutor | None = None
        self.replayer: StateReplayer | None = None
        self._semantic_engine: SemanticEngine | None = None
        self._max_states: int = int(max_states if max_states is not None else getattr(settings, "MAX_STATES", 1000))
        self._max_transitions: int = int(max_transitions if max_transitions is not None else getattr(settings, "MAX_TRANSITIONS", 5000))
        self._state_count: int = int(initial_state_count)
        self._transition_count: int = int(initial_transition_count)

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
            graph_store=self.graph_builder,
            graph_id=self.graph_id,
            session_id=self.session_id,
        )
        self.executor = EventExecutor(
            self.browser,
            config_path=self.config_path,
            input_defaults=input_config,
            semantic_engine=self._semantic_engine,
        )
        self.replayer = StateReplayer(
            self.browser,
            self.executor,
            self.graph_builder,
            self.graph_id,
            self._settings,
        )

        logger.info("Crawl session initialized")

    def _resolved_input_config(self) -> dict:
        return resolve_input_defaults(self.config_path, self._input_defaults)

    async def cleanup(self) -> None:
        await self.browser.stop()
        logger.info("Crawl session completed")

    async def add_to_queue(
        self,
        state: AbstractState,
        *,
        enqueue: bool = True,
        semantic_priority_penalty: float | None = None,
        matched_state_hash: str = "",
        confidence: float | None = None,
        reason: str = "",
        scores: dict | None = None,
    ) -> bool:
        await self._wait_permission()
        created = await self.graph_builder.add_state(
            self.graph_id,
            state,
            enqueue=enqueue,
            session_id=self.session_id,
            semantic_priority_penalty=semantic_priority_penalty,
            matched_state_hash=matched_state_hash,
            confidence=confidence,
            reason=reason,
            scores=scores,
        )
        state.html = ""
        if created:
            self._state_count += 1
        return created

    async def get_next_state(self) -> AbstractState | None:
        await self._wait_permission()
        return await self.graph_builder.claim_next_pending_state(self.graph_id, session_id=self.session_id)

    async def add_transition(self, transition: AbstractTransition) -> None:
        await self._wait_permission()
        created = await self.graph_builder.add_transition(transition)
        if created:
            self._transition_count += 1

    @property
    def is_complete(self) -> bool:
        return False

    def _within_limits(self) -> bool:
        return self._state_count < self._max_states and self._transition_count < self._max_transitions

    def _stop_requested_now(self) -> bool:
        return bool(self._stop_requested and self._stop_requested.is_set())

    def _slice_expired(self) -> bool:
        return self._slice_deadline_monotonic is not None and time.monotonic() >= self._slice_deadline_monotonic

    def _can_continue(self) -> bool:
        return self._within_limits() and not self._stop_requested_now() and not self._slice_expired()

    async def run_crawl(self) -> None:
        try:
            await self.initialize()
            await self._seed_initial_state()

            while self._can_continue():
                await self._wait_permission()
                current = await self.get_next_state()
                if current:
                    logger.info(
                        f"Exploring state {current.state_hash} "
                        f"({self._state_count}/{self._max_states} states, "
                        f"{self._transition_count}/{self._max_transitions} transitions)"
                    )
                    await self._explore_state(current)
                    continue

                if self._settings.DEFER_DESTRUCTIVE_ACTIONS:
                    item = await self.graph_builder.claim_deferred_work(
                        self.graph_id,
                        session_id=self.session_id,
                    )
                    if item:
                        await self._run_deferred_item(item)
                        continue

                break

            if self._slice_expired():
                logger.info("Crawl slice deadline reached; yielding session %s", self.session_id)
            elif self._stop_requested_now():
                logger.info("Crawl stop requested; yielding session %s", self.session_id)

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
            await self._semantic_engine.register_state(initial_state.state_hash, initial_elements)

        await self.add_to_queue(initial_state, enqueue=not bool(login_actions))

        info = StateReplayInfo(
            checkpoint_url=initial_state.url,
            checkpoint_state_hash=initial_state.state_hash,
            checkpoint_kind="initial",
        )
        updated = await self.replayer.register(initial_state.state_hash, info)
        if updated:
            await self._persist_replay_artifacts(
                state_hash=initial_state.state_hash,
                info=info,
                persist_storage_state=True,
            )
        logger.info(f"Initial state: {initial_state.state_hash} at {initial_state.url}")

        if login_actions:
            await self._mark_login_state(initial_state)
            reached = await self._execute_action_sequence(initial_state, info, login_actions)
            if not reached:
                await self.graph_builder.mark_state_pending(
                    self.graph_id,
                    initial_state.state_hash,
                    session_id=self.session_id,
                )

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
            if self._is_login_form(form):
                return form
        return None

    def _is_login_form(self, form: dict) -> bool:
        fields = form.get("fields", [])
        has_password = any(str(f.get("type", "")).lower() == "password" for f in fields)
        submit = form.get("submit")

        return bool(has_password and submit and submit.get("selector"))

    async def _mark_login_state(self, state: AbstractState) -> None:
        state.metadata = dict(state.metadata or {})
        state.metadata["is_login_state"] = True

        await self.graph_builder.set_state_properties(
            self.graph_id,
            state.state_hash,
            {"is_login_state": True},
        )

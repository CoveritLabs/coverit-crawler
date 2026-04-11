import hashlib
import json
import logging
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Set
from uuid import uuid4

from ..browser.engine import BrowserEngine
from ..config import config
from ..models.graph import AbstractState, AbstractTransition, CrawlAction
from .executor import EventExecutor, StateReplayer, StateReplayInfo
from .fingerprints import (
    action_attempt_fingerprint,
    best_effort_action_value,
    transition_fingerprint,
)
from .risk import RiskClassifier, is_http_url, is_non_http_href

logger = logging.getLogger(__name__)


@dataclass
class DeferredWorkItem:
    source_state: AbstractState
    actions: List[CrawlAction]
    element: Optional[dict] = None


class CrawlSession:
    def __init__(
        self,
        base_url: str,
        graph_builder,
        config_path: Optional[str] = None,
        session_id: Optional[str] = None,
        headless: bool = False,
    ):
        self.base_url = base_url
        self.graph_builder = graph_builder
        self.headless = headless
        self.config_path = config_path
        self.session_id = session_id or str(uuid4())

        self.discovered_states: Set[str] = set()
        self.discovery_queue: Deque[AbstractState] = deque()
        self._deferred_work: Deque[DeferredWorkItem] = deque()
        self._tried_actions_by_state: Dict[str, Set[str]] = {}
        self._seen_transition_ids: Set[str] = set()
        self._risk = RiskClassifier.from_config()
        self._login_attempts = 0

        self.browser = BrowserEngine(headless=headless)
        self.executor: Optional[EventExecutor] = None
        self.replayer: Optional[StateReplayer] = None
        self._max_states: int = 100
        self._max_transitions: int = 500
        self._state_count: int = 0
        self._transition_count: int = 0

    async def initialize(self) -> None:
        await self.browser.start()
        self.executor = EventExecutor(self.browser, self.config_path)
        self.replayer = StateReplayer(self.browser, self.executor)
        logger.info("Crawl session initialized")

    async def cleanup(self) -> None:
        await self.browser.stop()
        logger.info("Crawl session completed")

    async def add_to_queue(self, state: AbstractState) -> None:
        if state.state_hash in self.discovered_states:
            return
        self._state_count += 1
        self.discovered_states.add(state.state_hash)
        self.discovery_queue.append(state)
        await self.graph_builder.add_state(self.session_id, state)

    def get_next_state(self) -> Optional[AbstractState]:
        return self.discovery_queue.popleft() if self.discovery_queue else None

    async def add_transition(self, transition: AbstractTransition) -> None:
        if transition.transition_id in self._seen_transition_ids:
            return
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

    async def run_crawl(self, max_states: int = 100, max_transitions: int = 500) -> None:
        self._max_states = max_states
        self._max_transitions = max_transitions
        try:
            await self.initialize()
            await self._seed_initial_state()

            while self._within_limits():
                if not self.is_complete:
                    current = self.get_next_state()
                    if current:
                        logger.info(
                            f"Exploring state {current.state_hash} "
                            f"({self._state_count}/{max_states} states, "
                            f"{self._transition_count}/{max_transitions} transitions)"
                        )
                        await self._explore_state(current)
                    continue

                if config.DEFER_DESTRUCTIVE_ACTIONS and self._deferred_work:
                    item = self._deferred_work.popleft()
                    await self._run_deferred_item(item)
                    continue

                break

            logger.info(
                f"Crawl complete. States: {self._state_count}, "
                f"Transitions: {self._transition_count}"
            )
        except Exception as e:
            logger.error(f"Crawl failed: {e}", exc_info=True)
            raise
        finally:
            await self.cleanup()

    async def _seed_initial_state(self) -> None:
        await self.browser.navigate(self.base_url)
        await self.browser.wait_for_settle()

        await self._attempt_login_if_needed()
        await self.browser.wait_for_settle()

        initial_state = await self.browser.capture_state()
        if not self.replayer:
            return
        self.replayer.register(
            initial_state.state_hash,
            StateReplayInfo(checkpoint_url=initial_state.url),
        )
        await self.add_to_queue(initial_state)
        logger.info(f"Initial state: {initial_state.state_hash} at {initial_state.url}")

    async def _attempt_login_if_needed(self) -> None:
        if not config.LOGIN_USERNAME or not config.LOGIN_PASSWORD:
            return
        if self._login_attempts >= 2:
            return
        if not self.executor:
            return

        forms = await self.browser.get_forms()
        login_form = self._select_login_form(forms)
        if not login_form:
            return

        self._login_attempts += 1
        actions = self.executor.plan_form_submission(
            login_form,
            overrides={"username": config.LOGIN_USERNAME, "password": config.LOGIN_PASSWORD},
        )
        if not actions:
            return

        for action in actions:
            await self.executor.execute_action(action)

    def _select_login_form(self, forms: List[dict]) -> Optional[dict]:
        for form in forms:
            fields = form.get("fields", [])
            if any(str(f.get("type", "")).lower() == "password" for f in fields):
                submit = form.get("submit")
                if submit and submit.get("selector"):
                    return form
        return None

    async def _explore_state(self, current: AbstractState) -> None:
        if not self.replayer:
            return
        try:
            ok = await self.replayer.replay_to(current.state_hash)
            if not ok:
                return
        except Exception as e:
            logger.warning(f"Replay failed for state {current.state_hash}: {e}")
            return

        await self.browser.wait_for_settle()
        await self._attempt_login_if_needed()
        await self.browser.wait_for_settle()

        current_info = self.replayer.get_info(current.state_hash)
        if not current_info or not self.executor:
            return

        forms = await self.browser.get_forms()
        for form in forms:
            if not self._within_limits():
                break
            await self._process_form(form, current, current_info)
            try:
                await self.replayer.replay_to(current.state_hash)
            except Exception:
                return

        elements = await self.browser.get_interactable_elements()
        processed = 0
        for element in elements:
            if processed >= config.MAX_ELEMENTS_PER_STATE:
                break
            if not self._within_limits():
                break
            if not self._should_process_element(element):
                continue
            await self._process_element(element, current, current_info)
            processed += 1

    async def _process_form(self, form: dict, current: AbstractState, current_info: StateReplayInfo) -> None:
        if not self.executor:
            return

        actions = self.executor.plan_form_submission(form)
        if not actions:
            return

        primary = actions[-1]
        if config.DEFER_DESTRUCTIVE_ACTIONS and self._risk.is_risky(primary, element=form.get("submit")):
            self._deferred_work.append(DeferredWorkItem(source_state=current, actions=actions, element=form.get("submit")))
            return

        await self._execute_action_sequence(current, current_info, actions, element=form.get("submit"))

    async def _process_element(self, element: dict, current: AbstractState, current_info: StateReplayInfo) -> None:
        selector = self.browser.get_selector_for_element(element)
        if not selector:
            return

        sequences = self._plan_element_sequences(element, selector)
        for actions in sequences:
            if not self._within_limits():
                return
            primary = actions[-1]
            if config.DEFER_DESTRUCTIVE_ACTIONS and self._risk.is_risky(primary, element=element):
                self._deferred_work.append(DeferredWorkItem(source_state=current, actions=actions, element=element))
                continue
            await self._execute_action_sequence(current, current_info, actions, element=element)
            if self.replayer:
                try:
                    await self.replayer.replay_to(current.state_hash)
                except Exception:
                    return

    def _should_process_element(self, element: dict) -> bool:
        if element.get("disabled"):
            return False

        tag = str(element.get("tag", "") or "").lower()
        input_type = str(element.get("type", "") or "").lower()

        if element.get("in_form"):
            if tag == "select":
                return True
            if tag == "input" and input_type in ("checkbox", "radio"):
                return True
            return False

        if tag == "a" and not config.CLICK_NON_HTTP_LINKS:
            href = str(element.get("href", "") or "")
            if is_non_http_href(href):
                return False

        return True

    def _plan_element_sequences(self, element: dict, selector: str) -> List[List[CrawlAction]]:
        tag = str(element.get("tag", "") or "").lower()
        input_type = str(element.get("type", "") or "").lower()
        frame = element.get("frame")

        if tag == "select":
            options = [o for o in element.get("options", []) if o.get("value")]
            out: List[List[CrawlAction]] = []
            for o in options[: config.MAX_SELECT_OPTIONS_PER_ELEMENT]:
                out.append([
                    CrawlAction(
                        action_type="select",
                        selector=selector,
                        value=str(o["value"]),
                        description=f"Select '{o.get('text', o['value'])}'",
                        metadata={"option": str(o.get("text", "")), "frame": frame},
                    )
                ])
            return out

        if tag == "input" and input_type in ("checkbox", "radio"):
            return [[
                CrawlAction(
                    action_type="click",
                    selector=selector,
                    description=f"Toggle {input_type}",
                    metadata={"type": input_type, "frame": frame},
                )
            ]]

        if tag in ("input", "textarea") or element.get("contenteditable"):
            if not self.executor:
                return []
            value = self.executor.resolve_value(element)

            sequences: List[List[CrawlAction]] = []
            sequences.append([
                CrawlAction(
                    action_type="type",
                    selector=selector,
                    value=value,
                    description="Type input",
                    metadata={"type": input_type, "frame": frame},
                )
            ])

            if tag == "input" and input_type in ("text", "search", "email", "tel", "url", "number"):
                sequences.append([
                    CrawlAction(
                        action_type="type",
                        selector=selector,
                        value=value,
                        description="Type input",
                        metadata={"type": input_type, "frame": frame},
                    ),
                    CrawlAction(
                        action_type="press",
                        selector=selector,
                        value="Enter",
                        description="Press Enter",
                        metadata={"frame": frame},
                    ),
                ])

            return sequences

        return [[
            CrawlAction(
                action_type="click",
                selector=selector,
                description=f"Click {tag}",
                metadata={"frame": frame},
            )
        ]]

    async def _execute_action_sequence(
        self,
        source: AbstractState,
        source_info: StateReplayInfo,
        actions: List[CrawlAction],
        *,
        element: Optional[dict] = None,
    ) -> None:
        if not self.executor or not self.replayer:
            return
        if not actions:
            return

        primary = actions[-1]
        primary.metadata = dict(primary.metadata or {})
        primary.metadata["sequence_digest"] = self._sequence_digest(actions)
        primary.metadata["sequence_len"] = len(actions)

        attempt_fp = action_attempt_fingerprint(source.state_hash, primary)
        tried = self._tried_actions_by_state.setdefault(source.state_hash, set())
        if attempt_fp in tried:
            return
        tried.add(attempt_fp)

        initial_page_count = len(self.browser.context.pages) if self.browser.context else 0

        try:
            for action in actions:
                await self.executor.execute_action(action)

            await self.browser.wait_for_settle()

            popup_urls = await self.browser.collect_and_close_pages_opened_since(initial_page_count)
            for url in popup_urls:
                if not url or not is_http_url(url):
                    continue
                if not self.browser.is_same_domain(source_info.checkpoint_url, url):
                    continue
                nav_action = CrawlAction(
                    action_type="navigate",
                    value=url,
                    description="Navigate to popup URL",
                )
                self._deferred_work.append(DeferredWorkItem(source_state=source, actions=[nav_action], element=None))

            new_url = await self.browser.get_current_url()
            if not self.browser.is_same_domain(source_info.checkpoint_url, new_url):
                logger.warning(f"Left domain: {new_url}")
                await self.replayer.replay_to(source.state_hash)
                return

            new_state = await self.browser.capture_state()
            if new_state.state_hash == source.state_hash:
                return

            self.replayer.register(
                new_state.state_hash,
                self._build_replay_info(source_info, actions),
            )
            await self.add_to_queue(new_state)
            await self.add_transition(self._build_transition(source, new_state, primary))

        except Exception as e:
            logger.warning(f"Error on action sequence ({primary.action_type}): {e}")
            try:
                await self.replayer.replay_to(source.state_hash)
            except Exception:
                pass

    def _build_transition(self, source: AbstractState, target: AbstractState, action: CrawlAction) -> AbstractTransition:
        fp = transition_fingerprint(
            session_id=str(self.session_id),
            source_state_hash=source.state_hash,
            target_state_hash=target.state_hash,
            action=action,
        )
        locator_value = action.selector or action.value
        return AbstractTransition(
            session_id=str(self.session_id),
            transition_id=fp,
            source_state_hash=source.state_hash,
            target_state_hash=target.state_hash,
            action_type=action.action_type,
            action_description=action.description,
            locator_id=action.action_id,
            locator_value=locator_value,
            action_value=best_effort_action_value(action),
            action_fingerprint=fp,
        )

    def _build_replay_info(self, current_info: StateReplayInfo, actions: List[CrawlAction]) -> StateReplayInfo:
        return StateReplayInfo(
            checkpoint_url=current_info.checkpoint_url,
            actions=current_info.actions + list(actions),
        )

    def _sequence_digest(self, actions: List[CrawlAction]) -> str:
        payload = [{"t": a.action_type, "s": a.selector, "v": a.value} for a in actions]
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def _run_deferred_item(self, item: DeferredWorkItem) -> None:
        if not self.replayer:
            return
        try:
            ok = await self.replayer.replay_to(item.source_state.state_hash)
            if not ok:
                return
        except Exception:
            return

        source_info = self.replayer.get_info(item.source_state.state_hash)
        if not source_info:
            return

        await self._execute_action_sequence(item.source_state, source_info, item.actions, element=item.element)
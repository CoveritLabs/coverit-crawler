import logging
from collections import deque
from typing import Deque, List, Optional, Set

from ..models.graph import AbstractState, AbstractTransition, CrawlAction
from ..browser.engine import BrowserEngine
from ..config import config
from .executor import EventExecutor, StateReplayer, StateReplayInfo

logger = logging.getLogger(__name__)


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
        self.session_id = session_id

        self.discovered_states: Set[str] = set()
        self.discovery_queue: Deque[AbstractState] = deque()
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
        logger.info(f"Crawl session initialized")

    async def cleanup(self) -> None:
        await self.browser.stop()
        logger.info(f"Crawl session completed")

    async def add_to_queue(self, state: AbstractState) -> None:
        if state.state_hash not in self.discovered_states:
            self._state_count += 1
            self.discovered_states.add(state.state_hash)
            self.discovery_queue.append(state)
            await self.graph_builder.add_state(self.session_id, state)

    def get_next_state(self) -> Optional[AbstractState]:
        return self.discovery_queue.popleft() if self.discovery_queue else None

    async def add_transition(self, transition: AbstractTransition) -> None:
        self._transition_count += 1
        await self.graph_builder.add_transition(transition)
        self.executor.log_transition(transition)

    @property
    def is_complete(self) -> bool:
        return not self.discovery_queue

    def _within_limits(self) -> bool:
        return (
            self._state_count < self._max_states
            and self._transition_count < self._max_transitions
        )

    async def run_crawl(self, max_states: int = 100, max_transitions: int = 500) -> None:
        self._max_states = max_states
        self._max_transitions = max_transitions
        try:
            await self.initialize()
            await self._seed_initial_state()

            while not self.is_complete and self._within_limits():
                current = self.get_next_state()
                if not current:
                    break
                logger.info(
                    f"Exploring state {current.state_hash} "
                    f"({self._state_count}/{max_states} states, "
                    f"{self._transition_count}/{max_transitions} transitions)"
                )
                await self._explore_state(current)

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
        
        initial_state = await self.browser.capture_state()
        self.replayer.register(
            initial_state.state_hash,
            StateReplayInfo(checkpoint_url=initial_state.url),
        )
        await self.add_to_queue(initial_state)
        logger.info(f"Initial state: {initial_state.state_hash} at {initial_state.url}")

    async def _explore_state(self, current: AbstractState) -> None:
        await self.replayer.replay_to(current.state_hash)

        await self.browser.wait_for_navigation()
        forms = await self.browser.get_forms()
        for form in forms:
            if not self._within_limits():
                break
            await self._process_form(form, current)
            await self.replayer.replay_to(current.state_hash)

        elements = await self.browser.get_interactable_elements()
        for element in elements[: config.MAX_ELEMENTS_PER_STATE]:
            if not self._within_limits():
                break
            if element.get("in_form"):
                continue
            await self._process_element(element, current)

    async def _process_form(self, form: dict, current: AbstractState) -> None:
        current_info = self.replayer.get_info(current.state_hash)
        try:
            submit_action = await self.executor.fill_and_submit_form(form)
            if not submit_action:
                return

            await self.browser.wait_for_navigation()

            new_url = await self.browser.get_current_url()
            if not self.browser.is_same_domain(current_info.checkpoint_url, new_url):
                await self.browser.go_back()
                return

            new_state = await self.browser.capture_state()

            if new_state.state_hash == current.state_hash:
                return

            self.replayer.register(
                new_state.state_hash,
                self._build_replay_info(current_info, new_state, submit_action),
            )
            await self.add_to_queue(new_state)
            await self.add_transition(self._build_transition(current, new_state, submit_action))
            logger.info(f"Form '{form.get('form_id')}' -> state {new_state.state_hash}")

        except Exception as e:
            logger.warning(f"Error processing form '{form.get('form_id')}': {e}")
            try:
                await self.replayer.replay_to(current.state_hash)
            except Exception:
                pass

    async def _process_element(self, element: dict, current: AbstractState) -> None:
        selector = self.browser.get_selector_for_element(element)
        if not selector:
            return

        tag = element.get("tag", "")
        if tag == "select":
            actions = self._build_select_actions(element, selector, current.state_hash)
        else:
            actions = [CrawlAction(
                action_id=f"{current.state_hash}-{element['id']}",
                action_type="click",
                selector=selector,
                description=f"Click {tag} '{element.get('text', '')[:30]}'",
            )]

        for action in actions:
            if not self._within_limits():
                break
            await self._try_action(action, current)
            await self.replayer.replay_to(current.state_hash)

    def _build_select_actions(
        self, element: dict, selector: str, state_hash: str
    ) -> List[CrawlAction]:
        options = [o for o in element.get("options", []) if o.get("value")]
        return [
            CrawlAction(
                action_id=f"{state_hash}-select-{selector}-{o['value']}",
                action_type="select",
                selector=selector,
                value=o["value"],
                description=f"Select '{o['text']}' in {selector}",
            )
            for o in options[: config.MAX_SELECT_OPTIONS_PER_ELEMENT]
        ]

    async def _try_action(self, action: CrawlAction, current: AbstractState) -> None:
        current_info = self.replayer.get_info(current.state_hash)
        try:
            initial_page_count = len(self.browser.context.pages)
            await self.executor.execute_action(action)
            await self.browser.wait_for_navigation()

            if await self._close_new_tabs(initial_page_count):
                return

            new_url = await self.browser.get_current_url()
            if not self.browser.is_same_domain(current_info.checkpoint_url, new_url):
                logger.warning(f"Left domain: {new_url}, going back")
                await self.browser.go_back()
                return

            new_state = await self.browser.capture_state()

            if new_state.state_hash == current.state_hash:
                return

            self.replayer.register(
                new_state.state_hash,
                self._build_replay_info(current_info, new_state, action),
            )
            await self.add_to_queue(new_state)
            await self.add_transition(self._build_transition(current, new_state, action))

        except Exception as e:
            logger.warning(f"Error on action '{action.action_id}': {e}")

    async def _close_new_tabs(self, initial_count: int) -> bool:
        closed_count = await self.browser.close_pages_opened_since(initial_count)
        if closed_count:
            logger.info(f"Closing {closed_count} new tab(s)")
            return True
        return False

    def _build_transition(
        self,
        source: AbstractState,
        target: AbstractState,
        action: CrawlAction,
    ) -> AbstractTransition:
        return AbstractTransition(
            transition_id=f"{source.state_hash}-{target.state_hash}",
            source_state_hash=source.state_hash,
            target_state_hash=target.state_hash,
            action_type=action.action_type,
            action_description=action.description,
            locator_id=action.action_id,
            locator_value=action.selector,
        )

    def _build_replay_info(
        self,
        current_info: StateReplayInfo,
        new_state: AbstractState,
        action: CrawlAction,
    ) -> StateReplayInfo:
        if new_state.url != current_info.checkpoint_url:
            return StateReplayInfo(checkpoint_url=new_state.url)
        return StateReplayInfo(
            checkpoint_url=current_info.checkpoint_url,
            actions=current_info.actions + [action],
        )
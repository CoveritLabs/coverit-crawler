import logging
from datetime import datetime, timezone
from typing import Optional, Set
from uuid import UUID
import asyncio

from ..models.domain import CrawlSession
from ..models.graph import AbstractState, AbstractTransition, CrawlAction
from ..browser.engine import BrowserEngine
from .executor import EventExecutor, StateReplayer, StateReplayInfo

logger = logging.getLogger(__name__)


class CrawlSessionManager:
    def __init__(
        self,
        session: CrawlSession,
        app_version_id: UUID,
        base_url: str,
        repository,
        graph_builder,
        headless: bool = False,
    ):
        self.session = session
        self.app_version_id = app_version_id
        self.base_url = base_url
        self.repository = repository
        self.graph_builder = graph_builder
        self.headless = headless

        self.discovered_states: Set[str] = set()
        self.discovery_queue: list = []
        self.browser = BrowserEngine(headless=headless, timeout_ms=30000)
        self.executor: Optional[EventExecutor] = None
        self.replayer: Optional[StateReplayer] = None

    async def initialize(self) -> None:
        self.session.status = "RUNNING"
        self.session.started_at = datetime.now(timezone.utc)
        await self.repository.crawl_sessions.create(self.session)
        await self.browser.start()
        self.executor = EventExecutor(self.browser)
        self.replayer = StateReplayer(self.browser, self.executor)
        logger.info(f"Crawl session {self.session.crawl_session_id} initialized")

    async def cleanup(self) -> None:
        await self.browser.stop()
        self.session.status = "COMPLETED"
        self.session.finished_at = datetime.now(timezone.utc)
        await self.repository.crawl_sessions.update_status(
            self.session.crawl_session_id,
            self.session.status,
            self.session.finished_at,
        )
        logger.info(f"Crawl session {self.session.crawl_session_id} completed")

    async def mark_failed(self) -> None:
        self.session.status = "FAILED"
        self.session.finished_at = datetime.now(timezone.utc)
        await self.repository.crawl_sessions.update_status(
            self.session.crawl_session_id,
            self.session.status,
            self.session.finished_at,
        )
        logger.error(f"Crawl session {self.session.crawl_session_id} failed")

    async def add_to_queue(self, state: AbstractState) -> None:
        if state.state_hash not in self.discovered_states:
            self.discovered_states.add(state.state_hash)
            self.discovery_queue.append(state)
            self.session.state_count += 1
            await self.graph_builder.add_state(self.session.crawl_session_id, state)
            logger.debug(f"Added state {state.state_id} to queue (total: {self.session.state_count})")

    def get_next_state(self) -> Optional[AbstractState]:
        if self.discovery_queue:
            return self.discovery_queue.pop(0)
        return None

    async def add_transition(self, transition: AbstractTransition) -> None:
        self.session.transition_count += 1
        await self.graph_builder.add_transition(transition)
        self.executor.log_transition(transition)
        logger.debug(f"Recorded transition: {transition.action_type}")

    @property
    def is_complete(self) -> bool:
        return len(self.discovery_queue) == 0

    async def run_crawl(self, max_states: int = 100, max_transitions: int = 500) -> None:
        try:
            await self.initialize()

            logger.info(f"Starting crawl from {self.base_url}")
            await self.browser.navigate(self.base_url)
            initial_state = await self.browser.capture_state()

            self.replayer.register(initial_state.state_id, StateReplayInfo(checkpoint_url=initial_state.url))
            await self.add_to_queue(initial_state)
            logger.info(f"Initial state captured: {initial_state.state_id}")

            while not self.is_complete and self.session.state_count < max_states and self.session.transition_count < max_transitions:
                current = self.get_next_state()
                if not current:
                    logger.info("No more states to explore.")
                    break

                logger.info(f"Exploring state {current.state_id} ({self.session.state_count}/{max_states})")

                current_info = self.replayer.get_info(current.state_id)
                await self.replayer.replay_to(current.state_id)
                elements = await self.browser.get_interactable_elements()
                logger.debug(f"Found {len(elements)} interactable elements on {current.url}")

                for element in elements[:2]:                    
                    if self.session.transition_count >= max_transitions:
                        break

                    selector = self.browser.get_selector_for_element(element)
                    if not selector:
                        continue

                    try:
                        action = CrawlAction(
                            action_id=f"{current.state_id}-{element['id']}",
                            action_type="click",
                            selector=selector,
                            description=f"Click {element.get('tag')} with text '{element.get('text')}'",
                        )

                        initial_pages_count = len(self.browser.context.pages)

                        await self.executor.execute_action(action)
                        await self.browser.wait_for_navigation()

                        # figure out a better way to handle this
                        await asyncio.sleep(2)
                        current_pages = self.browser.context.pages

                        if len(current_pages) > initial_pages_count:
                            logger.info("Action opened new tab, closing.")
                            for new_page in current_pages[initial_pages_count:]:
                                try:
                                    await new_page.close()
                                except Exception as e:
                                    logger.debug(f"Failed to close new tab: {e}")
                                    
                            await self.replayer.replay_to(current.state_id)
                            continue

                        new_url = await self.browser.get_current_url()

                        if not self.browser._is_same_domain(current_info.checkpoint_url, new_url):
                            logger.warning(f"Navigated to different domain: {new_url}, going back")
                            await self.browser.go_back()
                            continue

                        new_state = await self.browser.capture_state()

                        if new_url != current_info.checkpoint_url:
                            new_info = StateReplayInfo(checkpoint_url=new_url)
                        else:
                            new_info = StateReplayInfo(
                                checkpoint_url=current_info.checkpoint_url,
                                actions=current_info.actions + [action],
                            )

                        self.replayer.register(new_state.state_id, new_info)

                        transition = AbstractTransition(
                            transition_id=f"{current.state_id}-{new_state.state_id}",
                            source_state_id=current.state_id,
                            target_state_id=new_state.state_id,
                            action_type=action.action_type,
                            action_description=action.description,
                            locator_id=action.action_id,
                            locator_value=selector,
                        )

                        await self.add_to_queue(new_state)
                        await self.add_transition(transition)
                        logger.info(f"Discovered new state: {new_state.state_id}")

                        await self.replayer.replay_to(current.state_id)

                    except Exception as e:
                        logger.warning(f"Error exploring element: {e}")
                        try:
                            await self.replayer.replay_to(current.state_id)
                        except Exception:
                            pass
                        continue

            logger.info(f"Crawl complete. States: {self.session.state_count}, Transitions: {self.session.transition_count}")

        except Exception as e:
            logger.error(f"Crawl failed with error: {e}", exc_info=True)
            await self.mark_failed()
            raise
        finally:
            await self.cleanup()
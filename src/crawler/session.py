"""Crawl session management."""

from typing import Optional, Set
from datetime import datetime, timezone
from uuid import UUID
import logging

from ..models.domain import CrawlSession
from ..models.graph import AbstractState, AbstractTransition, CrawlAction
from ..browser.engine import BrowserEngine
from .executor import EventExecutor

logger = logging.getLogger(__name__)


class CrawlSessionManager:
    """Manages a crawl session lifecycle."""

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
        self.executor = None
        self.current_state: Optional[AbstractState] = None

    async def initialize(self) -> None:
        """Start the crawl session."""
        self.session.status = "RUNNING"
        self.session.started_at = datetime.now(timezone.utc)
        await self.repository.crawl_sessions.create(self.session)
        await self.browser.start()
        self.executor = EventExecutor(self.browser)
        logger.info(f"Crawl session {self.session.crawl_session_id} initialized")

    async def cleanup(self) -> None:
        """Clean up session resources."""
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
        """Mark session as failed."""
        self.session.status = "FAILED"
        self.session.finished_at = datetime.now(timezone.utc)
        await self.repository.crawl_sessions.update_status(
            self.session.crawl_session_id,
            self.session.status,
            self.session.finished_at,
        )
        logger.error(f"Crawl session {self.session.crawl_session_id} failed")

    async def add_to_queue(self, state: AbstractState) -> None:
        """Add state to discovery queue."""
        if state.state_hash not in self.discovered_states:
            self.discovered_states.add(state.state_hash)
            self.discovery_queue.append(state)
            self.session.state_count += 1

            await self.graph_builder.add_state(self.session.crawl_session_id, state)
            logger.debug(f"Added state {state.state_id} to queue (total: {self.session.state_count})")

    def get_next_state(self) -> Optional[AbstractState]:
        """Get next state from discovery queue."""
        if self.discovery_queue:
            return self.discovery_queue.pop(0)
        return None

    async def add_transition(self, transition: AbstractTransition) -> None:
        """Add transition to graph."""
        self.session.transition_count += 1
        await self.graph_builder.add_transition(transition)
        self.executor.get_transition_log().append(transition)

        logger.debug(f"Recorded transition: {transition.action_type}")

    @property
    def is_complete(self) -> bool:
        """Check if crawl is complete."""
        return len(self.discovery_queue) == 0

    async def run_crawl(self, max_states: int = 100, max_transitions: int = 500) -> None:
        """Execute BFS crawl of application."""
        try:
            await self.initialize()

            logger.info(f"Starting crawl from {self.base_url}")
            await self.browser.navigate(self.base_url)

            initial_state = await self.browser.capture_state()
            await self.add_to_queue(initial_state)
            logger.info(f"Initial state captured: {initial_state.state_id}")

            while not self.is_complete and self.session.state_count < max_states and self.session.transition_count < max_transitions:
                current = self.get_next_state()
                if not current:
                    logger.info("No more states to explore.", self.discovery_queue)
                    break

                logger.info(f"Exploring state {current.state_id} ({self.session.state_count}/{max_states})")
                self.current_state = current

                if current.url != await self.browser.get_current_url():
                    await self.browser.navigate(current.url)

                elements = await self.browser.get_interactable_elements()
                logger.debug(f"Found {len(elements)} interactable elements on {current.url}")

                # limit elements per state for now
                for element in elements[:2]: 
                    if self.session.transition_count >= max_transitions:
                        break

                    if current.url != await self.browser.get_current_url():
                        await self.browser.navigate(current.url)
                    try:
                        selector = self._get_selector_for_element(element)
                        if not selector:
                            continue

                        logger.debug(f"Executing action: click on {element.get('tag')}")

                        action = CrawlAction(
                            action_id=f"{current.state_id}-{element['id']}",
                            action_type="click",
                            selector=selector,
                            description=f"Click {element.get('tag')} with text '{element.get('text')}'",
                        )

                        await self.executor.execute_action(action)
                        new_state = await self.browser.capture_state()

                        if new_state:
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
                        else:
                            logger.warning(f"Failed to execute action on {selector}")

                    except Exception as e:
                        logger.warning(f"Error exploring element: {e}")
                        try:
                            await self.browser.navigate(current.url)
                        except:
                            pass
                        continue

            logger.info(f"Crawl complete. States: {self.session.state_count}, Transitions: {self.session.transition_count}")

        except Exception as e:
            logger.error(f"Crawl failed with error: {e}", exc_info=True)
            await self.mark_failed()
            raise
        finally:
            await self.cleanup()

    def _get_selector_for_element(self, element: dict) -> Optional[str]:
        """Generate selector for an element."""
        tag = element.get("tag", "")
        text = element.get("text", "").strip()

        if tag in ["button", "a"] and text:
            return f'text="{text[:50]}"'

        selector = element.get("selector", "")
        if selector:
            return f"{selector}:first-child"

        if tag:
            return tag

        return None

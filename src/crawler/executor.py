"""Event execution and state transition logging."""

from typing import List, Optional

from .utils import capture_state
from ..models.graph import AbstractState, AbstractTransition, CrawlAction
from ..browser.engine import BrowserEngine


class EventExecutor:
    """Executes actions and logs state transitions."""

    def __init__(self, browser: BrowserEngine):
        self.browser = browser
        self.transition_log: List[AbstractTransition] = []

    async def execute_action(
        self, action: CrawlAction, source_state: AbstractState
    ) -> Optional[AbstractState]:
        """Execute action and capture resulting state."""
        try:
            if action.action_type == "click":
                await self.browser.click(action.selector)
            elif action.action_type == "type":
                await self.browser.type_text(action.selector, action.value)
            elif action.action_type == "navigate":
                await self.browser.navigate(action.value)
            else:
                return None

            await self.browser.wait_for_navigation()

            target_state = await capture_state(browser=self.browser)

            transition = AbstractTransition(
                transition_id=f"{source_state.state_id}-{target_state.state_id}",
                source_state_id=source_state.state_id,
                target_state_id=target_state.state_id,
                action_type=action.action_type,
                action_description=action.description,
                locator_id=action.action_id,
                locator_value=action.selector,
            )
            self.transition_log.append(transition)

            return target_state

        except Exception as e:
            print(f"Error executing action: {e}")
            return None

    def get_transition_log(self) -> List[AbstractTransition]:
        """Get log of all transitions."""
        return self.transition_log.copy()

"""Event execution and state transition logging."""

from typing import List, Optional

from ..models.graph import AbstractState, AbstractTransition, CrawlAction
from ..browser.engine import BrowserEngine


class EventExecutor:
    """Executes actions and logs state transitions."""

    def __init__(self, browser: BrowserEngine):
        self.browser = browser
        self.transition_log: List[AbstractTransition] = []

    async def execute_action(
        self, action: CrawlAction
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

        except Exception as e:
            print(f"Error executing action: {e}")
            return None

    def get_transition_log(self) -> List[AbstractTransition]:
        """Get log of all transitions."""
        return self.transition_log.copy()

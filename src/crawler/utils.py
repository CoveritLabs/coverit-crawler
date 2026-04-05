from ..models.graph import AbstractState
from datetime import datetime, timezone
from ..browser.engine import BrowserEngine

async def capture_state(browser: BrowserEngine) -> AbstractState:
        """Capture current page state."""
        state_hash = await browser.get_state_hash()
        url = await browser.get_current_url()
        title = await browser.get_page_title()
        content = await browser.get_page_content()
        interactable = await browser.get_interactable_elements()

        state = AbstractState(
            state_id=state_hash[:8],
            state_hash=state_hash,
            url=url,
            title=title,
            dom_snapshot={
                "content_length": len(content),
                "element_count": len(interactable),
            },
            metadata={
                "interactable_count": len(interactable),
                "timestamp": datetime.now(timezone.utc),
            },
        )
        return state
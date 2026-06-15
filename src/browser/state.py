from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from src.models import AbstractState


class StateManager:
    def __init__(self, browser):
        self._browser = browser

    async def capture(self) -> AbstractState:
        state_hash = await self._browser.get_state_hash()
        url = await self._browser.get_current_url()
        title = await self._browser.get_page_title()
        content = await self._browser.get_page_content()
        interactable = await self._browser.get_interactable_elements()

        return AbstractState(
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

    @staticmethod
    def hash_content(content: str) -> str:
        normalized = re.sub(
            r"\s+",
            " ",
            content.lower(),
        ).strip()

        normalized = re.sub(
            r"[\u0000-\u001f]+",
            " ",
            normalized,
        ).strip()

        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

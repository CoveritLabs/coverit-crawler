from __future__ import annotations

from typing import List, Optional, Callable

from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

class PageManager:
    def __init__(
        self,
        *,
        context_provider: Callable[[], BrowserContext],
        popup_timeout_ms: int,
    ):
        self._context_provider = context_provider
        self._popup_timeout_ms = popup_timeout_ms

    async def wait_for_new_page(
        self,
        timeout_ms: Optional[int] = None,
    ) -> Optional[Page]:
        timeout = int(timeout_ms if timeout_ms is not None else self._popup_timeout_ms)

        context = self._context()

        try:
            return await context.wait_for_event(
                "page",
                timeout=timeout,
            )
        except PlaywrightTimeoutError:
            return None

    async def collect_new_pages(
        self,
        initial_count: int,
        *,
        timeout_ms: Optional[int] = None,
    ) -> List[Page]:
        timeout = int(timeout_ms if timeout_ms is not None else self._popup_timeout_ms)

        context = self._context()

        if len(context.pages) <= initial_count:
            await self.wait_for_new_page(timeout_ms=timeout)

        return context.pages[initial_count:]

    def _context(self) -> BrowserContext:
        return self._context_provider()
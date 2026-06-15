from __future__ import annotations

from typing import Awaitable, Callable, Optional

from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    Page,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

Action = Callable[[], Awaitable[None]]


class BrowserActions:
    def __init__(
        self,
        *,
        page_provider,
        wait_for_settle,
        timeout_ms: int,
        retry_count: int,
    ):
        self._page_provider = page_provider
        self._wait_for_settle = wait_for_settle
        self._timeout_ms = timeout_ms
        self._retry_count = retry_count

    async def retry(
        self,
        action: Action,
        *,
        selector: str,
        fallback: Action | None = None,
    ) -> None:
        last_error: Optional[Exception] = None

        for attempt in range(self._retry_count + 1):
            try:
                await action()
                return

            except (
                PlaywrightTimeoutError,
                PlaywrightError,
            ) as e:
                last_error = e

                if attempt >= self._retry_count:
                    break

                if fallback:
                    try:
                        await fallback()
                        return
                    except Exception:
                        pass

                try:
                    await self._page.wait_for_selector(
                        selector,
                        state="visible",
                        timeout=min(self._timeout_ms, 3000),
                    )
                except Exception:
                    pass

                await self._wait_for_settle(load_state="domcontentloaded")

        if last_error:
            raise last_error

    @property
    def _page(self) -> Page:
        return self._page_provider()

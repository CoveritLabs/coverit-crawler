from __future__ import annotations

from typing import Any

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from src.browser.storage_state import normalize_storage_state


class BrowserRuntime:
    def __init__(self, *, headless: bool = True):
        self.headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    @property
    def browser(self) -> Browser | None:
        return self._browser

    async def start(self) -> None:
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)

    async def stop(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def new_context(self, storage_state: Any = None) -> BrowserContext:
        await self.start()
        if self._browser is None:
            raise RuntimeError("Browser runtime failed to start")

        normalized = normalize_storage_state(storage_state)
        if normalized is None:
            return await self._browser.new_context()
        return await self._browser.new_context(storage_state=normalized)

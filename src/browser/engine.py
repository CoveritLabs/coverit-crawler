from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)

from src.browser.actions import BrowserActions
from src.browser.frames import FrameResolver
from src.browser.page_manager import PageManager
from src.browser.state import StateManager
from src.browser.storage_state import normalize_storage_state
from src.browser.js_loader import JsLoader
from src.config import Config, config
from src.models import AbstractState
from src.utils import build_selector, attach_selectors_to_forms


class BrowserEngine:
    def __init__(
        self,
        headless: bool = True,
        timeout_ms: Optional[int] = None,
        settings: Config = config,
    ):
        self._settings = settings
        self.headless = headless
        self.timeout_ms = int(timeout_ms if timeout_ms is not None else settings.TIMEOUT_MS)

        self.page_load_state = str(
            getattr(settings, "PAGE_LOAD_STATE", "networkidle") or "networkidle"
        )

        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None

        js_dir = os.path.join(os.path.dirname(__file__), "js")
        self._js = JsLoader(js_dir)

        self._frames = FrameResolver(self._require_page)
        self._pages = PageManager(
            context_provider=self._require_context,
            popup_timeout_ms=settings.POPUP_TIMEOUT_MS,
        )
        self._state = StateManager(self)
        self._actions = BrowserActions(
            page_provider=self._require_page,
            wait_for_settle=self.wait_for_settle,
            timeout_ms=self.timeout_ms,
            retry_count=self._settings.ACTION_RETRY_COUNT,
        )

    async def start(self) -> None:
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.timeout_ms)

    async def start_with_storage_state(self, storage_state: Any = None) -> None:
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)

        normalized = normalize_storage_state(storage_state)

        if normalized is None:
            self.context = await self.browser.new_context()
        else:
            self.context = await self.browser.new_context(storage_state=normalized)

        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.timeout_ms)

    async def stop(self) -> None:
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def navigate(self, url: str) -> None:
        page = self._require_page()
        await page.goto(url, wait_until=self.page_load_state, timeout=self.timeout_ms)

    async def go_back(self) -> None:
        page = self._require_page()
        await page.go_back(wait_until=self.page_load_state, timeout=self.timeout_ms)

    async def click(
        self,
        selector: str,
        *,
        frame_url: Optional[str] = None,
        frame_name: Optional[str] = None,
    ) -> None:
        target = self._frames.resolve(frame_url=frame_url, frame_name=frame_name)

        await self._actions.retry(
            lambda: target.click(selector, timeout=self.timeout_ms),
            selector=selector,
        )

    async def type_text(
        self,
        selector: str,
        text: str,
        *,
        frame_url: Optional[str] = None,
        frame_name: Optional[str] = None,
    ) -> None:
        target = self._frames.resolve(frame_url=frame_url, frame_name=frame_name)
        page = self._require_page()

        async def action():
            await target.fill(selector, text, timeout=self.timeout_ms)

        async def fallback():
            await self.click(selector, frame_url=frame_url, frame_name=frame_name)
            await page.keyboard.press("Control+A")
            await page.keyboard.type(text)

        await self._actions.retry(action, selector=selector, fallback=fallback)

    async def select_option(
        self,
        selector: str,
        value: str,
        *,
        frame_url: Optional[str] = None,
        frame_name: Optional[str] = None,
    ) -> None:
        target = self._frames.resolve(frame_url=frame_url, frame_name=frame_name)

        await self._actions.retry(
            lambda: target.select_option(selector, value, timeout=self.timeout_ms),
            selector=selector,
        )

    async def press_key(
        self,
        selector: str,
        key: str,
        *,
        frame_url: Optional[str] = None,
        frame_name: Optional[str] = None,
    ) -> None:
        target = self._frames.resolve(frame_url=frame_url, frame_name=frame_name)

        await self._actions.retry(
            lambda: target.press(selector, key, timeout=self.timeout_ms),
            selector=selector,
        )

    async def wait_for_settle(
        self,
        *,
        load_state: Optional[str] = None,
        timeout_ms: Optional[int] = None,
    ) -> None:
        page = self._require_page()
        timeout = timeout_ms or self.timeout_ms

        try:
            await page.wait_for_load_state(
                load_state or self.page_load_state,
                timeout=timeout,
            )
        except Exception:
            pass

        if not self._settings.USE_DOM_QUIESCENCE:
            return

        try:
            await page.evaluate(
                self._js.load("wait_for_dom_quiescence.js"),
                {
                    "quietMs": int(self._settings.DOM_QUIET_MS),
                    "timeoutMs": int(self._settings.DOM_SETTLE_TIMEOUT_MS),
                },
            )
        except Exception:
            pass

    async def get_current_url(self) -> str:
        url = self._require_page().url
        return url[:-1] if url.endswith("?") else url

    async def get_page_title(self) -> str:
        return await self._require_page().title()

    async def get_page_content(self) -> str:
        return await self._require_page().content()

    async def get_state_hash(self) -> str:
        semantic = await self._evaluate_js(self._js.load("get_state_hash.js"))
        return self._state.hash_content(str(semantic))

    async def get_interactable_elements(self) -> List[Dict[str, Any]]:
        return await self._evaluate_js(self._js.load("get_interactable_elements.js"))

    async def get_forms(self) -> List[Dict[str, Any]]:
        raw = await self._evaluate_js(self._js.load("get_forms.js"))
        return attach_selectors_to_forms(raw)

    async def capture_state(self) -> AbstractState:
        return await self._state.capture()

    async def export_storage_state(self) -> Dict[str, Any]:
        return await self._require_context().storage_state()

    async def new_context_from_storage_state(self, storage_state: Any = None) -> BrowserContext:
        browser = self._require_browser()
        normalized = normalize_storage_state(storage_state)

        if normalized is None:
            return await browser.new_context()

        return await browser.new_context(storage_state=normalized)

    async def reset_context_from_storage_state(self, storage_state: Any = None) -> None:
        if self.context:
            await self.context.close()

        self.context = await self.new_context_from_storage_state(storage_state)
        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.timeout_ms)

    def get_selector_for_element(self, element: dict) -> str | None:
        return build_selector(element)

    async def wait_for_new_page(self, timeout_ms: Optional[int] = None):
        return await self._pages.wait_for_new_page(timeout_ms=timeout_ms)

    async def close_pages_opened_since(self, initial_count: int, timeout_ms: Optional[int] = None) -> int:
        pages = await self._pages.collect_new_pages(initial_count, timeout_ms=timeout_ms)

        for page in pages:
            try:
                await page.close()
            except Exception:
                pass

        return len(pages)

    async def collect_and_close_pages_opened_since(self, initial_count: int, *, timeout_ms: Optional[int] = None) -> List[str]:
        pages = await self._pages.collect_new_pages(initial_count, timeout_ms=timeout_ms)

        urls: List[str] = []

        for page in pages:
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass

            try:
                if page.url:
                    urls.append(page.url)
            except Exception:
                pass

            try:
                await page.close()
            except Exception:
                pass

        return urls

    async def _evaluate_js(self, js_code: str, *, retries: int = 1):
        page = self._require_page()
        attempt = 0

        while True:
            try:
                return await page.evaluate(js_code)
            except Exception:
                if attempt >= retries:
                    raise
                attempt += 1
                await page.wait_for_load_state(self.page_load_state, timeout=self.timeout_ms)

    def _require_browser(self) -> Browser:
        if not self.browser:
            raise RuntimeError("Browser not started")
        return self.browser

    def _require_context(self) -> BrowserContext:
        if not self.context:
            raise RuntimeError("Browser not started")
        return self.context

    def _require_page(self) -> Page:
        if not self.page:
            raise RuntimeError("Browser not started")
        return self.page
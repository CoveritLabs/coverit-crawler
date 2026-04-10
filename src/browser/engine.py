import hashlib
import re
import os
from src.utils import read_file
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from src.config import config

from playwright.async_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from ..models.graph import AbstractState


class BrowserEngine:
    def __init__(self, headless: bool = True, timeout_ms: int = config.TIMEOUT_MS):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.page_load_state = config.PAGE_LOAD_STATE
        self.js_dir_path = os.path.join(os.path.dirname(__file__), "js")
        self._js_cache: Dict[str, str] = {}
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None

    def _require_context(self) -> BrowserContext:
        if not self.context:
            raise RuntimeError("Browser not started")
        return self.context

    def _require_page(self) -> Page:
        if not self.page:
            raise RuntimeError("Browser not started")
        return self.page

    def _get_js_code(self, filename: str) -> str:
        cached = self._js_cache.get(filename)
        if cached is not None:
            return cached
        js_file = os.path.join(self.js_dir_path, filename)
        js_code = read_file(js_file)
        self._js_cache[filename] = js_code
        return js_code

    async def start(self) -> None:
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context()
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

    async def click(self, selector: str) -> None:
        page = self._require_page()
        await page.click(selector)

    async def type_text(self, selector: str, text: str) -> None:
        page = self._require_page()
        await page.fill(selector, text)

    async def select_option(self, selector: str, value: str) -> None:
        page = self._require_page()
        await page.select_option(selector, value)

    async def get_current_url(self) -> str:
        page = self._require_page()
        url = page.url
        if url.endswith("?"):
            url = url[:-1]
        return url

    async def get_page_title(self) -> str:
        page = self._require_page()
        return await page.title()

    async def get_page_content(self) -> str:
        page = self._require_page()
        return await page.content()

    async def wait_for_navigation(self) -> None:
        page = self._require_page()
        await page.wait_for_load_state(self.page_load_state, timeout=self.timeout_ms)

    async def wait_for_new_page(self, timeout_ms: int = 1000) -> Optional[Page]:
        context = self._require_context()
        try:
            return await context.wait_for_event("page", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            return None

    async def close_pages_opened_since(self, initial_count: int, timeout_ms: int = 1000) -> int:
        context = self._require_context()

        if len(context.pages) <= initial_count:
            await self.wait_for_new_page(timeout_ms=timeout_ms)

        extra_pages = context.pages[initial_count:]
        for page in extra_pages:
            try:
                await page.close()
            except Exception:
                pass
        return len(extra_pages)

    async def _evaluate_js(self, js_code: str, *, retries: int = 1) -> Any:
        page = self._require_page()

        attempt = 0
        while True:
            try:
                return await page.evaluate(js_code)
            except PlaywrightError as e:
                message = str(e)
                if attempt >= retries or "Execution context was destroyed" not in message:
                    raise
                attempt += 1
                await page.wait_for_load_state(
                    self.page_load_state, timeout=self.timeout_ms
                )

    async def take_screenshot(self, path: str) -> None:
        page = self._require_page()
        await page.screenshot(path=path)

    def is_same_domain(self, url1: str, url2: str) -> bool:
        return urlparse(url1).netloc == urlparse(url2).netloc

    def _is_same_domain(self, url1: str, url2: str) -> bool:
        return self.is_same_domain(url1, url2)

    def get_selector_for_element(self, element: dict) -> Optional[str]:
        tag = element.get("tag", "")
        el_id = element.get("id", "")
        name = element.get("name", "")
        text = element.get("text", "").strip()
        value = element.get("value", "")
        input_type = element.get("type", "")

        if el_id and not el_id.isdigit():
            return f"#{el_id}"
        if name:
            return f"[name='{name}']"
        if tag == "input" and input_type in ["submit", "button"] and value:
            return f'input[type="{input_type}"][value="{value}"]'
        if tag in ("button", "a") and text:
            return f'{tag}:has-text("{text[:50]}")'
        selector = element.get("selector", "")
        if selector:
            return selector

        return tag or None

    async def get_state_hash(self) -> str:
        self._require_page()
        js_code = self._get_js_code("get_state_hash.js")
        semantic_content = await self._evaluate_js(js_code)
        normalized = re.sub(r'\s+', ' ', semantic_content.lower())
        normalized = re.sub(r'[^a-z0-9|:]+', '', normalized)
        return hashlib.md5(normalized.encode()).hexdigest()
    
    async def get_interactable_elements(self) -> List[Dict[str, Any]]:
        self._require_page()
        js_code = self._get_js_code("get_interactable_elements.js")
        return await self._evaluate_js(js_code)
    
    async def get_forms(self) -> List[Dict[str, Any]]:
        self._require_page()
        js_code = self._get_js_code("get_forms.js")
        raw = await self._evaluate_js(js_code)

        for form in raw:
            for f in form["fields"]:
                f["selector"] = self.get_selector_for_element(f)
            if form.get("submit"):
                form["submit"]["selector"] = self.get_selector_for_element(form["submit"])

        return raw

    async def capture_state(self) -> AbstractState:
        state_hash = await self.get_state_hash()
        url = await self.get_current_url()
        title = await self.get_page_title()
        content = await self.get_page_content()
        interactable = await self.get_interactable_elements()

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
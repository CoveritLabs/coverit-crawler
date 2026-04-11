import hashlib
import re
import os
from src.utils import read_file
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from src.config import Config, config

from playwright.async_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Frame,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from ..models.graph import AbstractState


class BrowserEngine:
    def __init__(self, headless: bool = True, timeout_ms: Optional[int] = None, settings: Config = config):
        self._settings = settings
        self.headless = headless
        self.timeout_ms = int(timeout_ms if timeout_ms is not None else settings.TIMEOUT_MS)
        self.page_load_state = str(getattr(settings, "PAGE_LOAD_STATE", "networkidle") or "networkidle")
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

    def _resolve_frame(
        self,
        *,
        frame_url: Optional[str] = None,
        frame_name: Optional[str] = None,
    ) -> Optional[Frame]:
        page = self._require_page()

        if frame_name:
            try:
                frame = page.frame(name=frame_name)
                if frame:
                    return frame
            except Exception:
                pass

        if frame_url:
            try:
                for frame in page.frames:
                    if frame.url == frame_url or frame.url.startswith(frame_url):
                        return frame
            except Exception:
                return None

        return None

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

    async def click(
        self,
        selector: str,
        *,
        frame_url: Optional[str] = None,
        frame_name: Optional[str] = None,
    ) -> None:
        target = self._resolve_frame(frame_url=frame_url, frame_name=frame_name) or self._require_page()
        last_error: Optional[Exception] = None
        for attempt in range(self._settings.ACTION_RETRY_COUNT + 1):
            try:
                await target.click(selector, timeout=self.timeout_ms)
                return
            except (PlaywrightTimeoutError, PlaywrightError) as e:
                last_error = e
                if attempt >= self._settings.ACTION_RETRY_COUNT:
                    raise
                try:
                    await self._require_page().wait_for_selector(
                        selector, state="visible", timeout=min(self.timeout_ms, 3000)
                    )
                except Exception:
                    pass
                await self.wait_for_settle(load_state="domcontentloaded")
        if last_error:
            raise last_error

    async def type_text(
        self,
        selector: str,
        text: str,
        *,
        frame_url: Optional[str] = None,
        frame_name: Optional[str] = None,
    ) -> None:
        target = self._resolve_frame(frame_url=frame_url, frame_name=frame_name) or self._require_page()
        page = self._require_page()
        last_error: Optional[Exception] = None
        for attempt in range(self._settings.ACTION_RETRY_COUNT + 1):
            try:
                await target.fill(selector, text, timeout=self.timeout_ms)
                return
            except (PlaywrightTimeoutError, PlaywrightError) as e:
                last_error = e
                if attempt >= self._settings.ACTION_RETRY_COUNT:
                    break
                try:
                    await self.click(selector, frame_url=frame_url, frame_name=frame_name)
                    await page.keyboard.press("Control+A")
                    await page.keyboard.type(text)
                    return
                except Exception:
                    await self.wait_for_settle(load_state="domcontentloaded")
        if last_error:
            raise last_error

    async def select_option(
        self,
        selector: str,
        value: str,
        *,
        frame_url: Optional[str] = None,
        frame_name: Optional[str] = None,
    ) -> None:
        target = self._resolve_frame(frame_url=frame_url, frame_name=frame_name) or self._require_page()
        last_error: Optional[Exception] = None
        for attempt in range(self._settings.ACTION_RETRY_COUNT + 1):
            try:
                await target.select_option(selector, value, timeout=self.timeout_ms)
                return
            except (PlaywrightTimeoutError, PlaywrightError) as e:
                last_error = e
                if attempt >= self._settings.ACTION_RETRY_COUNT:
                    break
                await self.wait_for_settle(load_state="domcontentloaded")
        if last_error:
            raise last_error

    async def press_key(
        self,
        selector: str,
        key: str,
        *,
        frame_url: Optional[str] = None,
        frame_name: Optional[str] = None,
    ) -> None:
        target = self._resolve_frame(frame_url=frame_url, frame_name=frame_name) or self._require_page()
        last_error: Optional[Exception] = None
        for attempt in range(self._settings.ACTION_RETRY_COUNT + 1):
            try:
                await target.press(selector, key, timeout=self.timeout_ms)
                return
            except (PlaywrightTimeoutError, PlaywrightError) as e:
                last_error = e
                if attempt >= self._settings.ACTION_RETRY_COUNT:
                    break
                await self.wait_for_settle(load_state="domcontentloaded")
        if last_error:
            raise last_error

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
        await self.wait_for_settle()

    async def wait_for_settle(
        self,
        *,
        load_state: Optional[str] = None,
        timeout_ms: Optional[int] = None,
    ) -> None:
        page = self._require_page()
        timeout = timeout_ms or self.timeout_ms

        try:
            await page.wait_for_load_state(load_state or self.page_load_state, timeout=timeout)
        except PlaywrightTimeoutError:
            pass

        if not self._settings.USE_DOM_QUIESCENCE:
            return

        try:
            js_code = self._get_js_code("wait_for_dom_quiescence.js")
            await page.evaluate(
                js_code,
                {"quietMs": int(self._settings.DOM_QUIET_MS), "timeoutMs": int(self._settings.DOM_SETTLE_TIMEOUT_MS)},
            )
        except Exception:
            pass

    async def wait_for_new_page(self, timeout_ms: Optional[int] = None) -> Optional[Page]:
        context = self._require_context()
        timeout = int(timeout_ms if timeout_ms is not None else self._settings.POPUP_TIMEOUT_MS)
        try:
            return await context.wait_for_event("page", timeout=timeout)
        except PlaywrightTimeoutError:
            return None

    async def close_pages_opened_since(self, initial_count: int, timeout_ms: Optional[int] = None) -> int:
        context = self._require_context()

        timeout = int(timeout_ms if timeout_ms is not None else self._settings.POPUP_TIMEOUT_MS)

        if len(context.pages) <= initial_count:
            await self.wait_for_new_page(timeout_ms=timeout)

        extra_pages = context.pages[initial_count:]
        for page in extra_pages:
            try:
                await page.close()
            except Exception:
                pass
        return len(extra_pages)

    async def collect_and_close_pages_opened_since(
        self,
        initial_count: int,
        *,
        timeout_ms: Optional[int] = None,
    ) -> List[str]:
        context = self._require_context()

        timeout = int(timeout_ms if timeout_ms is not None else self._settings.POPUP_TIMEOUT_MS)

        if len(context.pages) <= initial_count:
            await self.wait_for_new_page(timeout_ms=timeout)

        extra_pages = context.pages[initial_count:]
        urls: List[str] = []
        for page in extra_pages:
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=min(timeout, 3000))
            except Exception:
                pass
            try:
                url = page.url
                if url:
                    urls.append(url)
            except Exception:
                pass
            try:
                await page.close()
            except Exception:
                pass

        return urls

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
        candidates = element.get("selector_candidates")
        if isinstance(candidates, list):
            for candidate in candidates:
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()

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
            safe_text = text[:50].replace("\\", "\\\\").replace('"', "\\\"")
            return f'{tag}:has-text("{safe_text}")'
        selector = element.get("selector", "")
        if selector:
            return selector

        return tag or None

    async def get_state_hash(self) -> str:
        self._require_page()
        js_code = self._get_js_code("get_state_hash.js")
        semantic_content = await self._evaluate_js(js_code)
        normalized = re.sub(r"\s+", " ", str(semantic_content).lower()).strip()
        normalized = re.sub(r"[\u0000-\u001f]+", " ", normalized).strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    
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
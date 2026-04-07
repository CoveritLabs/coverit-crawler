import hashlib
import re
from urllib.parse import urlparse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from ..models.graph import AbstractState


class BrowserEngine:
    def __init__(self, headless: bool = True, timeout_ms: int = 30000):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None

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
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.goto(url, wait_until="networkidle")

    def _is_same_domain(self, url1: str, url2: str) -> bool:
        return urlparse(url1).netloc == urlparse(url2).netloc

    async def go_back(self) -> None:
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.go_back()
        await self.page.wait_for_load_state("networkidle")

    async def get_page_title(self) -> str:
        if not self.page:
            raise RuntimeError("Browser not started")
        return await self.page.title()

    async def get_current_url(self) -> str:
        if not self.page:
            raise RuntimeError("Browser not started")
        return self.page.url

    async def click(self, selector: str) -> None:
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.click(selector)

    async def type_text(self, selector: str, text: str) -> None:
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.fill(selector, text)

    async def get_page_content(self) -> str:
        if not self.page:
            raise RuntimeError("Browser not started")
        return await self.page.content()

    async def get_state_hash(self) -> str:
        semantic_content = await self.page.evaluate("""() => {
            const body = document.body.cloneNode(true);

            const trackerTags = body.querySelectorAll('script, style, meta, noscript, link, iframe, svg');
            trackerTags.forEach(tag => tag.remove());

            let text = (body.innerText || "").toLowerCase().trim();
            text = text.replace(/\s+/g, ' ');

            const interactives = Array.from(body.querySelectorAll('button, a, input'))
                .map(el => {
                    const key = (el.name || '') + '|' + (el.type || '') + '|' + (el.placeholder || '');
                    return key.trim() ? key : '';
                })
                .filter(key => key)
                .sort()
                .join('|');

            return text + ':::' + interactives;
        }""")

        normalized = re.sub(r'\s+', ' ', semantic_content.lower())
        normalized = re.sub(r'[^a-z0-9|:]+', '', normalized)
        return hashlib.md5(normalized.encode()).hexdigest()

    async def get_interactable_elements(self) -> List[Dict[str, Any]]:
        if not self.page:
            raise RuntimeError("Browser not started")

        selector = "button, a, input, select, textarea, [role='button'], [onclick]"
        locator = self.page.locator(selector)
        count = await locator.count()
        elements: List[Dict[str, Any]] = []

        for i in range(count):
            el = locator.nth(i)
            if await el.is_visible():
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                text = await el.input_value() if tag in ("input", "textarea") else await el.inner_text()
                elements.append({
                    "id": await el.get_attribute("id") or str(i),
                    "tag": tag,
                    "text": text,
                    "type": await el.get_attribute("type") or "",
                    "selector": await el.evaluate(
                        """el => el.id ? `#${el.id}` : el.tagName.toLowerCase() + (el.className ? '.' + el.className.split(' ')[0] : '')"""
                    ),
                    "visible": True,
                })

        return elements

    async def wait_for_navigation(self) -> None:
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.wait_for_load_state("networkidle")

    async def take_screenshot(self, path: str) -> None:
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.screenshot(path=path)

    async def capture_state(self) -> AbstractState:
        state_hash = await self.get_state_hash()
        url = await self.get_current_url()
        title = await self.get_page_title()
        content = await self.get_page_content()
        interactable = await self.get_interactable_elements()

        return AbstractState(
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
    
    def get_selector_for_element(self, element: dict) -> Optional[str]:
        tag = element.get("tag", "")
        text = element.get("text", "").strip()

        if tag in ["button", "a"] and text:
            return f'text="{text[:50]}"'

        selector = element.get("selector", "")
        if selector:
            return f"{selector}:first-child"

        if tag:
            return tag

        return None
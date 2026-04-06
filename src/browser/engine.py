"""Playwright-based browser engine for crawling."""

import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from ..models.graph import AbstractState
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
import hashlib


class BrowserEngine:
    """Manages Playwright browser instance and page interactions."""

    def __init__(self, headless: bool = True, timeout_ms: int = 30000):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None

    async def start(self) -> None:
        """Initialize browser and page."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        # will probably change it, but for now it closes any new page that opens
        self.context.on("page", lambda page: page.close())
        self.page.set_default_timeout(self.timeout_ms)

    async def stop(self) -> None:
        """Close browser and cleanup."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def navigate(self, url: str) -> None:
        """Navigate to URL."""
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.goto(url, wait_until="networkidle")

    async def get_page_title(self) -> str:
        """Get current page title."""
        if not self.page:
            raise RuntimeError("Browser not started")
        return await self.page.title()

    async def get_current_url(self) -> str:
        """Get current page URL."""
        if not self.page:
            raise RuntimeError("Browser not started")
        return self.page.url

    async def click(self, selector: str) -> None:
        """Click on element."""
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.click(selector)

    async def type_text(self, selector: str, text: str) -> None:
        """Type text into element."""
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.fill(selector, text)

    async def get_page_content(self) -> str:
        """Get page HTML content."""
        if not self.page:
            raise RuntimeError("Browser not started")
        return await self.page.content()

    # async def get_state_hash(self) -> str:
    #     """Generate hash of normalized page state."""
    #     content = await self.get_page_content()
    #     normalized = content.replace("\n", "").replace("\t", "")
    #     return hashlib.md5(normalized.encode()).hexdigest()
    
    async def get_state_hash(self) -> str:
        """Generate hash of page state."""
    
        # semantic content for now
        semantic_content = await self.page.evaluate("""() => {
            const body = document.body.cloneNode(true);

            const trackerTags = body.querySelectorAll('script, style, meta, noscript, link, iframe, svg');
            trackerTags.forEach(tag => tag.remove());

            let text = body.innerText || "";
            
            const interactives = Array.from(body.querySelectorAll('button, a, input'))
                .map(el => {
                    const key = (el.name || '') + '|' + (el.type || '') + '|' + (el.placeholder || '');
                    return key.length > 2 ? key : '';  
                })
                .filter(key => key)
                .sort()  
                .join('|');

            return text + ':::' + interactives; 
        }""")

        normalized = re.sub(r'\W+', '', semantic_content)
        return hashlib.md5(normalized.encode()).hexdigest()

    async def get_interactable_elements(self) -> List[Dict[str, Any]]:
        """Get list of interactable elements on the page using Playwright built-ins."""
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
                text = ""
                if tag in ("input", "textarea"):
                    text = await el.input_value()
                else:
                    text = (await el.inner_text())[:100]  

                element_data: Dict[str, Any] = {
                    "id": await el.get_attribute("id") or str(i),
                    "tag": tag,
                    "text": text,
                    "type": await el.get_attribute("type") or "",
                    "selector": await el.evaluate(
                        """el => el.id ? `#${el.id}` : el.tagName.toLowerCase() + (el.className ? '.' + el.className.split(' ')[0] : '')"""
                    ),
                    "visible": True
                }
                elements.append(element_data)

        return elements

    async def wait_for_navigation(self) -> None:
        """Wait for page navigation."""
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.wait_for_load_state("networkidle")

    async def take_screenshot(self, path: str) -> None:
        """Take screenshot of current page."""
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.screenshot(path=path)

    async def capture_state(self) -> AbstractState:
        """Capture current page state."""
        state_hash = await self.get_state_hash()
        url = await self.get_current_url()
        title = await self.get_page_title()
        content = await self.get_page_content()
        interactable = await self.get_interactable_elements()

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

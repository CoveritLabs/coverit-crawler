import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from src.config import config

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from ..models.graph import AbstractState


class BrowserEngine:
    def __init__(self, headless: bool = True, timeout_ms: int = config.TIMEOUT_MS):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.page_load_state = config.PAGE_LOAD_STATE
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
        await self.page.goto(url, wait_until=self.page_load_state, timeout=self.timeout_ms)

    async def go_back(self) -> None:
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.go_back(wait_until=self.page_load_state, timeout=self.timeout_ms)

    async def click(self, selector: str) -> None:
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.click(selector, no_wait_after=True)

    async def type_text(self, selector: str, text: str) -> None:
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.fill(selector, text, no_wait_after=True)

    async def select_option(self, selector: str, value: str) -> None:
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.select_option(selector, value, no_wait_after=True)

    async def get_current_url(self) -> str:
        if not self.page:
            raise RuntimeError("Browser not started")
        return self.page.url

    async def get_page_title(self) -> str:
        if not self.page:
            raise RuntimeError("Browser not started")
        return await self.page.title()

    async def get_page_content(self) -> str:
        if not self.page:
            raise RuntimeError("Browser not started")
        return await self.page.content()

    async def wait_for_navigation(self) -> None:
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.wait_for_load_state(self.page_load_state, timeout=self.timeout_ms)

    async def take_screenshot(self, path: str) -> None:
        if not self.page:
            raise RuntimeError("Browser not started")
        await self.page.screenshot(path=path)

    def _is_same_domain(self, url1: str, url2: str) -> bool:
        return urlparse(url1).netloc == urlparse(url2).netloc

    def _build_selector(self, element: dict) -> str:
        tag = element.get("tag", "")
        el_id = element.get("id")
        name = element.get("name")
        text = (element.get("text") or "").strip()
        value = element.get("value", "")
        input_type = element.get("type", "")

        if el_id:
            return f"#{el_id}"
        if name:
            return f"[name='{name}']"
        if tag == "input" and input_type == "submit" and value:
            return f'input[type="submit"][value="{value}"]'
        if tag == "input" and value:
            return f'{tag}[value="{value}"]'
        if text and tag in ["button", "a"]:
            return f'{tag}:has-text("{text[:50]}")'
        if text:
            return f'text="{text[:50]}"'
        return tag or "input"

    async def get_state_hash(self) -> str:
        semantic_content = await self.page.evaluate(r"""() => {
            const body = document.body.cloneNode(true);
            body.querySelectorAll('script, style, meta, noscript, link, iframe, svg').forEach(el => el.remove());
            let text = (body.innerText || '').toLowerCase().trim().replace(/\s+/g, ' ');
            const interactives = Array.from(body.querySelectorAll('button, a, input'))
                .map(el => `${el.name || ''}|${el.type || ''}|${el.placeholder || ''}`.trim())
                .filter(Boolean)
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

        return await self.page.evaluate("""() => {
            const formEls = new Set(
                Array.from(document.querySelectorAll('form input, form select, form textarea, form button'))
            );

            const labelFor = el => {
                if (el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) return lbl.innerText.trim();
                }
                const parent = el.closest('label');
                return parent ? parent.innerText.trim() : '';
            };

            const elements = Array.from(document.querySelectorAll(
                "button, a[href], input, select, textarea, [role='button'], [onclick]"
            ))
            .filter(el => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && !el.hidden;
            });

            const uniqueElements = [];
            const seenSignatures = new Set();

            elements.forEach((el, i) => {
                const tag = el.tagName.toLowerCase();
                const text = (tag === 'input' ? '' : (el.innerText || '')).trim();
                const type = (el.type || '').toLowerCase();
                const name = el.name || '';
                const href = el.href || '';
                const firstClass = el.className && typeof el.className === 'string' 
                    ? el.className.trim().split(/\s+/)[0] 
                    : '';

                const signature = `${tag}|${text}|${type}|${name}|${firstClass}|${href}`;

                if (!seenSignatures.has(signature)) {
                    seenSignatures.add(signature);
                    
                    uniqueElements.push({
                        id: el.id || String(i),
                        tag: tag,
                        text: text,
                        value: (tag === 'input' ? (el.value || '') : ''),
                        type: type,
                        name: name,
                        placeholder: el.placeholder || '',
                        label: labelFor(el),
                        href: href,
                        in_form: formEls.has(el),
                        options: tag === 'select'
                            ? Array.from(el.options).map(o => ({ value: o.value, text: o.text.trim() }))
                            : [],
                        selector: el.id
                            ? `#${el.id}`
                            : tag + (firstClass ? '.' + firstClass : ''),
                    });
                }
            });

            return uniqueElements;
        }""")

    async def get_forms(self) -> List[Dict[str, Any]]:
        if not self.page:
            raise RuntimeError("Browser not started")

        raw = await self.page.evaluate("""() => {
            const labelFor = el => {
                if (el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) return lbl.innerText.trim();
                }
                const parent = el.closest('label');
                return parent ? parent.innerText.trim() : '';
            };

            const toField = el => ({
                tag: el.tagName.toLowerCase(),
                id: el.id || '',
                name: el.name || '',
                type: (el.type || '').toLowerCase(),
                placeholder: el.placeholder || '',
                label: labelFor(el),
                checked: !!el.checked,
                options: el.tagName.toLowerCase() === 'select'
                    ? Array.from(el.options).map(o => ({ value: o.value, text: o.text.trim() }))
                    : [],
            });

            const toSubmit = el => el ? {
                tag: el.tagName.toLowerCase(),
                id: el.id || '',
                name: el.name || '',
                type: (el.type || '').toLowerCase(),
                value: el.value || '',
                text: (el.innerText || el.value || '').trim(),
            } : null;

            return Array.from(document.querySelectorAll('form')).map((form, i) => ({
                form_id: form.id || `form-${i}`,
                fields: Array.from(
                    form.querySelectorAll('input, select, textarea')
                ).map(toField),
                submit: toSubmit(
                    form.querySelector(
                        'button[type="submit"], input[type="submit"], button:not([type])'
                    )
                ),
            }));
        }""")

        for form in raw:
            for f in form["fields"]:
                f["selector"] = self._build_selector(f)
            if form.get("submit"):
                form["submit"]["selector"] = self._build_selector(form["submit"])

        return raw

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
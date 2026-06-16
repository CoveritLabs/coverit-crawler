from __future__ import annotations

import csv
import hashlib
import json
import logging
import random
from pathlib import Path
from typing import Any

from src.browser import BrowserEngine
from src.crawler.semantic_engine.extractor import DOMFeatureExtractor
from src.utils import is_same_domain, normalize_url, stable_json_dumps

logger = logging.getLogger(__name__)

RAW_FIELDS = (
    "flattened_text",
    "tag",
    "type",
    "id",
    "name",
    "text",
    "value",
    "placeholder",
    "label",
    "aria_label",
    "role",
    "topic_label",
)


class SemanticDataCollector:
    def __init__(
        self,
        raw_output: Path,
        state_output: Path,
        *,
        max_pages_per_domain: int,
        max_actions_per_page: int,
        timeout_ms: int,
        headless: bool,
    ):
        self.raw_output = raw_output
        self.state_output = state_output
        self.max_pages_per_domain = max_pages_per_domain
        self.max_actions_per_page = max_actions_per_page
        self.timeout_ms = timeout_ms
        self.headless = headless
        self._extractor = DOMFeatureExtractor()
        self._seen_elements: set[str] = set()
        self._seen_states: set[str] = set()

    async def collect(self, urls: list[str]) -> None:
        self._initialize_outputs()
        browser = BrowserEngine(
            headless=self.headless,
            timeout_ms=self.timeout_ms,
        )
        await browser.start()
        try:
            for index, url in enumerate(urls, start=1):
                logger.info("Collecting %s/%s: %s", index, len(urls), url)
                await self._collect_domain(browser, url)
        finally:
            await browser.stop()

    def _initialize_outputs(self) -> None:
        self.raw_output.parent.mkdir(parents=True, exist_ok=True)
        self.state_output.parent.mkdir(parents=True, exist_ok=True)
        with self.raw_output.open("w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=RAW_FIELDS).writeheader()
        self.state_output.write_text("", encoding="utf-8")

    async def _collect_domain(
        self,
        browser: BrowserEngine,
        start_url: str,
    ) -> None:
        queue = [normalize_url(start_url)]
        visited: set[str] = set()
        while queue and len(visited) < self.max_pages_per_domain:
            url = queue.pop(0)
            if not url or url in visited:
                continue
            visited.add(url)
            try:
                await self._navigate(browser, url)
                elements = await browser.get_interactable_elements()
            except Exception as exc:
                logger.warning("Skipping %s: %s", url, exc)
                continue

            self._write_elements(elements)
            await self._write_state(browser, elements, url, "initial")

            for href in self._same_domain_links(elements, start_url):
                if href not in visited and href not in queue:
                    queue.append(href)

            actions = self._safe_actions(browser, elements)
            for index, action in enumerate(
                actions[: self.max_actions_per_page],
                start=1,
            ):
                try:
                    await self._navigate(browser, url)
                    await self._execute_action(browser, action)
                    await browser.wait_for_settle(timeout_ms=self.timeout_ms)
                    changed = await browser.get_interactable_elements()
                    self._write_elements(changed)
                    await self._write_state(
                        browser,
                        changed,
                        url,
                        f"{index}:{action['kind']}",
                    )
                except Exception:
                    continue

    async def _navigate(self, browser: BrowserEngine, url: str) -> None:
        try:
            await browser.navigate(url)
        except Exception:
            if browser.page is None:
                raise
            await browser.page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
        await browser.wait_for_settle(timeout_ms=self.timeout_ms)

    def _write_elements(self, elements: list[dict[str, Any]]) -> None:
        rows = []
        for element in elements:
            flattened = self._extractor.extract(element)
            if not flattened or flattened in self._seen_elements:
                continue
            self._seen_elements.add(flattened)
            rows.append(
                {
                    "flattened_text": flattened,
                    "tag": element.get("tag", ""),
                    "type": element.get("type", ""),
                    "id": element.get("id", ""),
                    "name": element.get("name", ""),
                    "text": element.get("text", ""),
                    "value": element.get("value", ""),
                    "placeholder": element.get("placeholder", ""),
                    "label": element.get("label", ""),
                    "aria_label": element.get("aria_label", ""),
                    "role": element.get("role", ""),
                    "topic_label": "",
                }
            )
        if not rows:
            return
        with self.raw_output.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=RAW_FIELDS)
            writer.writerows(rows)

    async def _write_state(
        self,
        browser: BrowserEngine,
        elements: list[dict[str, Any]],
        source_url: str,
        action: str,
    ) -> None:
        current_url = await browser.get_current_url()
        state_id = hashlib.sha256(
            stable_json_dumps(
                {"url": current_url, "elements": elements}
            ).encode("utf-8")
        ).hexdigest()
        if state_id in self._seen_states:
            return
        self._seen_states.add(state_id)
        rows = [
            {
                "state_id": state_id,
                "url": current_url,
                "source_url": source_url,
                "action": action,
                "elements": elements,
            }
        ]
        if len(elements) > 1:
            reordered = list(elements)
            random.Random(state_id).shuffle(reordered)
            augmented_id = f"{state_id}-order"
            self._seen_states.add(augmented_id)
            rows.append(
                {
                    "state_id": augmented_id,
                    "url": current_url,
                    "source_url": source_url,
                    "action": f"{action}:order",
                    "augmentation_of": state_id,
                    "elements": reordered,
                }
            )
        with self.state_output.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(
                    json.dumps(row, ensure_ascii=True, default=str) + "\n"
                )

    def _same_domain_links(
        self,
        elements: list[dict[str, Any]],
        start_url: str,
    ) -> list[str]:
        links = []
        for element in elements:
            href = normalize_url(str(element.get("href", "") or ""))
            if (
                href.startswith(("http://", "https://"))
                and is_same_domain(start_url, href)
            ):
                links.append(href)
        return list(dict.fromkeys(links))

    def _safe_actions(
        self,
        browser: BrowserEngine,
        elements: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        actions = []
        for element in elements:
            selector = browser.get_selector_for_element(element)
            if not selector or element.get("disabled"):
                continue
            tag = str(element.get("tag", "") or "").lower()
            input_type = str(element.get("type", "") or "").lower()
            if tag == "select":
                current = str(element.get("value", "") or "")
                option = next(
                    (
                        item
                        for item in element.get("options", [])
                        if str(item.get("value", "") or "")
                        and str(item.get("value", "") or "") != current
                    ),
                    None,
                )
                if option:
                    actions.append(
                        {
                            "kind": "select",
                            "selector": selector,
                            "value": str(option["value"]),
                            "frame": element.get("frame"),
                        }
                    )
            elif tag == "input" and input_type in {"checkbox", "radio"}:
                actions.append(
                    {
                        "kind": "click",
                        "selector": selector,
                        "frame": element.get("frame"),
                    }
                )
            elif self._is_safe_button(element):
                actions.append(
                    {
                        "kind": "click",
                        "selector": selector,
                        "frame": element.get("frame"),
                    }
                )
        return actions

    def _is_safe_button(self, element: dict[str, Any]) -> bool:
        if str(element.get("tag", "") or "").lower() == "a":
            return False
        if str(element.get("type", "") or "").lower() == "submit":
            return False
        text = " ".join(
            str(element.get(key, "") or "").lower()
            for key in ("text", "label", "aria_label", "name", "id")
        )
        blocked = {
            "buy",
            "cancel",
            "checkout",
            "delete",
            "logout",
            "pay",
            "purchase",
            "remove",
            "submit",
        }
        return not any(word in text for word in blocked) and bool(
            element.get("aria_expanded")
            or str(element.get("role", "") or "").lower() == "button"
        )

    async def _execute_action(
        self,
        browser: BrowserEngine,
        action: dict[str, Any],
    ) -> None:
        frame = action.get("frame")
        frame_url = (
            frame.get("url") or frame.get("src")
            if isinstance(frame, dict)
            else None
        )
        frame_name = frame.get("name") if isinstance(frame, dict) else None
        if action["kind"] == "select":
            await browser.select_option(
                action["selector"],
                action["value"],
                frame_url=frame_url,
                frame_name=frame_name,
            )
        else:
            await browser.click(
                action["selector"],
                frame_url=frame_url,
                frame_name=frame_name,
            )

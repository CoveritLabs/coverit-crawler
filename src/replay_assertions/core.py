from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from src.browser import BrowserEngine
from src.crawler.executor import EventExecutor
from src.models import CrawlAction

logger = logging.getLogger(__name__)

_START_ASSERTION_SCRIPT = """
(() => {
  if (window.__coveritAssertionRecording) {
    return { recording: true, alreadyRunning: true, count: (window.__coveritAssertions || []).length };
  }
  window.__coveritAssertionRecording = true;
  window.__coveritAssertions = [];

  function getSelector(el) {
    if (!el || el === document.body) return 'body';
    if (el.id) return `#${el.id}`;
    const testId = el.getAttribute('data-testid') || el.getAttribute('data-test') || el.getAttribute('data-cy');
    if (testId) return `[data-testid="${testId}"]`;
    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel) return `${el.tagName.toLowerCase()}[aria-label="${ariaLabel}"]`;
    const path = [];
    let current = el;
    while (current && current !== document.body) {
      let selector = current.tagName.toLowerCase();
      if (current.id) {
        selector = `#${current.id}`;
        path.unshift(selector);
        break;
      }
      let sibling = current;
      let nth = 1;
      while ((sibling = sibling.previousElementSibling)) {
        if (sibling.tagName === current.tagName) nth += 1;
      }
      if (nth > 1) selector += `:nth-of-type(${nth})`;
      path.unshift(selector);
      current = current.parentElement;
    }
    return path.join(' > ');
  }

  window.__coveritAssertionHandler = function (e) {
    if (!window.__coveritAssertionRecording || !e.ctrlKey) return;
    e.preventDefault();
    e.stopPropagation();
    const el = e.target;
    window.__coveritAssertions.push({
      selector: getSelector(el),
      tag: (el.tagName || '').toLowerCase(),
      label: (el.innerText || '').trim().slice(0, 100) || el.getAttribute('aria-label') || '',
      url: location.href,
      timestamp: Date.now()
    });
  };

  document.addEventListener('click', window.__coveritAssertionHandler, true);
  return { recording: true, alreadyRunning: false, count: 0 };
})();
"""

_STOP_ASSERTION_SCRIPT = """
(() => {
  const assertions = Array.isArray(window.__coveritAssertions) ? window.__coveritAssertions : [];
  if (window.__coveritAssertionHandler) {
    document.removeEventListener('click', window.__coveritAssertionHandler, true);
  }
  window.__coveritAssertionRecording = false;
  return assertions;
})();
"""


async def _terminal_input(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


async def run_interactive_replay(
    checkpoint_url: str,
    storage_state: Any | None,
    transitions: list[dict[str, Any]],
    output_file: str = "artifacts/captured_assertions.json",
) -> None:
    """
    Replays a specific flow with headless=False, stopping after each transition
    to optionally capture assertions, and saves them mapped by transition_id.
    """
    browser = BrowserEngine(headless=False)
    executor = EventExecutor(browser)

    captured_data: dict[str, list[dict[str, Any]]] = {}

    try:
        if storage_state:
            await browser.start_with_storage_state(storage_state)
        else:
            await browser.start()
        logger.info("Navigating to checkpoint: %s", checkpoint_url)
        await browser.navigate(checkpoint_url)
        await browser.wait_for_settle()
        page = browser.page
        if not page:
            logger.error("Browser page failed to initialize.")
            return
        for step_idx, t in enumerate(transitions, start=1):
            trans_id = t.get("transition_id")
            if not trans_id:
                logger.warning("Skipping step with missing transition_id")
                continue

            action = CrawlAction(
                action_type=t.get("action_type", ""),
                selector=t.get("selector", ""),
                value=t.get("value", ""),
                description=t.get("description", ""),
            )

            logger.info("Step %d/%d: %s", step_idx, len(transitions), action.description)
            await executor.execute_action(action)
            await browser.wait_for_settle()

            captured_data[trans_id] = []

            while True:
                prompt = f"[Step {step_idx}] Assertions for {trans_id}? (Enter=skip, a=assert, q=quit) > "
                command = (await _terminal_input(prompt)).strip().lower()

                if command in {"", "s", "skip"}:
                    break
                elif command in {"q", "quit"}:
                    logger.info("Aborting replay early.")
                    _save_results(output_file, captured_data)
                    return
                elif command in {"a", "assert"}:
                    await page.evaluate(_START_ASSERTION_SCRIPT)
                    print("Assertion mode ON: Ctrl+Click elements in Chrome.")
                    await _terminal_input("Press Enter when done capturing assertions > ")

                    captured = await page.evaluate(_STOP_ASSERTION_SCRIPT)
                    if isinstance(captured, list):
                        captured_data[trans_id].extend(captured)
                        print(f"Captured {len(captured)} assertions for this step.")
                    break
                else:
                    print("Unknown command. Use Enter, a, or q.")

    finally:
        await browser.stop()
        _save_results(output_file, captured_data)


def _save_results(output_file: str, data: dict[str, Any]) -> None:
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Saved captured assertions to %s", out_path.absolute())

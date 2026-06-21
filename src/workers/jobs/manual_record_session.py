from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import aiohttp
from playwright.async_api import async_playwright

from src.config import config
from src.db.repositories.crawl_sessions import (
    fetch_job_inputs,
    mark_aborted_if_active,
    mark_completed_if_running,
    mark_failed_if_running,
    mark_finished_at_if_aborted,
)
from src.db.services.crawl_sessions import ensure_started_or_skip_aborted
from src.models import CrawlJob
from src.workers.jobs.crawl_session import _build_payload_from_db


logger = logging.getLogger(__name__)

VIEWPORT_WIDTH = 1365
VIEWPORT_HEIGHT = 768

DOM_RECORDER_SCRIPT = """
(() => {
  if (globalThis.__coveritFlowRecorderInstalled) return;
  globalThis.__coveritFlowRecorderInstalled = true;

  function escapeCss(value) {
    if (globalThis.CSS && typeof globalThis.CSS.escape === "function") {
      return globalThis.CSS.escape(value);
    }
    return String(value).replace(/["\\\\]/g, "\\\\$&");
  }

  function elementText(element) {
    if (!element) return "";
    const tag = element.tagName?.toLowerCase();
    const type = element.getAttribute?.("type")?.toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || type === "password") {
      return "";
    }
    return (element.innerText || element.textContent || "")
      .trim()
      .replace(/\\s+/g, " ")
      .slice(0, 160);
  }

  function selectorFor(element) {
    if (!(element instanceof Element)) return "unknown";
    const testId =
      element.getAttribute("data-testid") ||
      element.getAttribute("data-test") ||
      element.getAttribute("data-cy");
    if (testId) return `[data-testid="${escapeCss(testId)}"]`;
    if (element.id) return `#${escapeCss(element.id)}`;

    const ariaLabel = element.getAttribute("aria-label");
    if (ariaLabel) {
      return `${element.tagName.toLowerCase()}[aria-label="${escapeCss(ariaLabel)}"]`;
    }

    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 6) {
      let part = current.tagName.toLowerCase();
      if (current.id) {
        part += `#${escapeCss(current.id)}`;
        parts.unshift(part);
        break;
      }

      const classes = [...current.classList]
        .filter((className) => className && !/^\\d/.test(className))
        .slice(0, 2);
      for (const className of classes) {
        part += `.${escapeCss(className)}`;
      }

      const parent = current.parentElement;
      if (parent) {
        const siblings = [...parent.children].filter((child) => child.tagName === current.tagName);
        if (siblings.length > 1) {
          part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
        }
      }

      parts.unshift(part);
      current = current.parentElement;
    }
    return parts.join(" > ");
  }

  function accessibleName(element) {
    if (!(element instanceof Element)) return "";
    return (
      element.getAttribute("aria-label") ||
      element.getAttribute("title") ||
      element.getAttribute("alt") ||
      ""
    ).slice(0, 160);
  }

  function basePayload(action, event) {
    const element = event.target instanceof Element ? event.target : null;
    const rect = element?.getBoundingClientRect?.();
    const link = element?.closest?.("a");
    return {
      action,
      x: Math.round(event.clientX || 0),
      y: Math.round(event.clientY || 0),
      pageX: Math.round(event.pageX || 0),
      pageY: Math.round(event.pageY || 0),
      button: event.button ?? null,
      tag: element?.tagName?.toLowerCase() || null,
      selector: selectorFor(element),
      text: elementText(element),
      accessibleName: accessibleName(element),
      href: link?.href || null,
      elementBox: rect
        ? {
            x: Math.round(rect.x),
            y: Math.round(rect.y),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
          }
        : null,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
      },
    };
  }

  document.addEventListener(
    "click",
    (event) => {
      globalThis.__recordFlowEvent(basePayload("click", event)).catch(() => {});
    },
    true,
  );

  document.addEventListener(
    "change",
    (event) => {
      const payload = basePayload("change", event);
      const element = event.target instanceof Element ? event.target : null;
      const type = element?.getAttribute?.("type")?.toLowerCase();
      payload.value =
        type === "password" ? null : String(element?.value ?? "").slice(0, 160);
      globalThis.__recordFlowEvent(payload).catch(() => {});
    },
    true,
  );
})();
"""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _api_internal_ws_url(session_id: str) -> str:
    value = os.getenv("COVERIT_API_INTERNAL_WS_URL") or os.getenv("COVERIT_API_INTERNAL_URL")
    if not value:
        raise ValueError("COVERIT_API_INTERNAL_URL is required")

    base = value.rstrip("/")
    if base.startswith("http://"):
        base = f"ws://{base[7:]}"
    elif base.startswith("https://"):
        base = f"wss://{base[8:]}"

    return f"{base}/internal/ws/manual-recordings/{session_id}"


def _internal_token() -> str:
    token = os.getenv("INTERNAL_SERVICE_TOKEN", "").strip()
    if not token:
        raise ValueError("INTERNAL_SERVICE_TOKEN is required")
    return token


def _source_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


async def _install_dom_recorder(context: Any, session_id: str, flow_started: asyncio.Event, event_queue: asyncio.Queue[dict[str, Any]]) -> None:
    async def record_flow_event(source: Any, payload: Any) -> None:
        if not flow_started.is_set() or not isinstance(payload, dict):
            return

        source_page = _source_value(source, "page")
        source_frame = _source_value(source, "frame")
        event = {
            "id": str(uuid4()),
            "sessionId": session_id,
            "timestamp": _utc_now(),
            "pageUrl": str(getattr(source_page, "url", "") or ""),
            "frameUrl": str(getattr(source_frame, "url", "") or ""),
            **payload,
        }
        await event_queue.put(event)

    await context.expose_binding("__recordFlowEvent", record_flow_event)
    await context.add_init_script(DOM_RECORDER_SCRIPT)


async def _send_ws(ws: aiohttp.ClientWebSocketResponse, send_lock: asyncio.Lock, payload: dict[str, Any]) -> None:
    if ws.closed:
        return
    async with send_lock:
        if not ws.closed:
            await ws.send_json(payload)


async def _event_sender(
    ws: aiohttp.ClientWebSocketResponse,
    send_lock: asyncio.Lock,
    event_queue: asyncio.Queue[dict[str, Any]],
) -> None:
    while True:
        event = await event_queue.get()
        await _send_ws(ws, send_lock, {"type": "recorded.event", "event": event})


async def _start_screencast(
    page: Any,
    ws: aiohttp.ClientWebSocketResponse,
    send_lock: asyncio.Lock,
) -> tuple[Any, set[asyncio.Task[None]]]:
    cdp = await page.context.new_cdp_session(page)
    pending: set[asyncio.Task[None]] = set()

    await cdp.send("Page.enable")

    async def handle_frame(frame: dict[str, Any]) -> None:
        try:
            data = frame.get("data")
            if data:
                await _send_ws(
                    ws,
                    send_lock,
                    {
                        "type": "browser.frame",
                        "dataUrl": f"data:image/jpeg;base64,{data}",
                        "metadata": frame.get("metadata") or {},
                        "viewport": {
                            "width": VIEWPORT_WIDTH,
                            "height": VIEWPORT_HEIGHT,
                        },
                    },
                )
        finally:
            session_id = frame.get("sessionId")
            if session_id is not None:
                try:
                    await cdp.send("Page.screencastFrameAck", {"sessionId": session_id})
                except Exception:
                    pass

    def on_frame(frame: dict[str, Any]) -> None:
        task = asyncio.create_task(handle_frame(frame))
        pending.add(task)
        task.add_done_callback(pending.discard)

    cdp.on("Page.screencastFrame", on_frame)
    await cdp.send(
        "Page.startScreencast",
        {
            "format": "jpeg",
            "quality": 70,
            "maxWidth": VIEWPORT_WIDTH,
            "maxHeight": VIEWPORT_HEIGHT,
            "everyNthFrame": 1,
        },
    )
    return cdp, pending


async def _stop_screencast(cdp: Any | None, pending: set[asyncio.Task[None]]) -> None:
    if cdp is not None:
        try:
            await cdp.send("Page.stopScreencast")
        except Exception:
            pass

    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def _normalize_button(value: Any) -> str:
    if value == 1:
        return "middle"
    if value == 2:
        return "right"
    if value in {"left", "middle", "right"}:
        return str(value)
    return "left"


async def _handle_mouse_input(page: Any, input_payload: dict[str, Any]) -> None:
    action = str(input_payload.get("action") or "")
    x = round(float(input_payload.get("x") or 0))
    y = round(float(input_payload.get("y") or 0))
    button = _normalize_button(input_payload.get("button"))

    if action == "move":
        await page.mouse.move(x, y)
    elif action == "down":
        await page.mouse.move(x, y)
        await page.mouse.down(button=button)
    elif action == "up":
        await page.mouse.move(x, y)
        await page.mouse.up(button=button)
    elif action == "wheel":
        await page.mouse.wheel(
            float(input_payload.get("deltaX") or 0),
            float(input_payload.get("deltaY") or 0),
        )


async def _handle_keyboard_input(page: Any, input_payload: dict[str, Any]) -> None:
    key = str(input_payload.get("key") or "")
    if not key:
        return

    modifiers = [
        ("Control", bool(input_payload.get("ctrlKey"))),
        ("Meta", bool(input_payload.get("metaKey"))),
        ("Alt", bool(input_payload.get("altKey"))),
        ("Shift", bool(input_payload.get("shiftKey")) and len(key) != 1),
    ]
    active_modifiers = [name for name, enabled in modifiers if enabled]

    for modifier in active_modifiers:
        await page.keyboard.down(modifier)

    try:
        if len(key) == 1 and not any(input_payload.get(name) for name in ("ctrlKey", "metaKey", "altKey")):
            await page.keyboard.insert_text(key)
        else:
            await page.keyboard.press(key)
    finally:
        for modifier in reversed(active_modifiers):
            await page.keyboard.up(modifier)


async def _handle_browser_input(page: Any, message: dict[str, Any]) -> None:
    input_payload = message.get("input")
    if not isinstance(input_payload, dict):
        input_payload = message

    kind = str(input_payload.get("kind") or input_payload.get("type") or "")
    if kind == "mouse":
        await _handle_mouse_input(page, input_payload)
    elif kind == "keyboard":
        await _handle_keyboard_input(page, input_payload)


async def _send_navigation(ws: aiohttp.ClientWebSocketResponse, send_lock: asyncio.Lock, page: Any) -> None:
    await _send_ws(
        ws,
        send_lock,
        {
            "type": "browser.navigation",
            "url": page.url,
            "title": await page.title(),
            "timestamp": _utc_now(),
        },
    )


async def manual_record_session(ctx: dict, session_id: str) -> dict[str, Any]:
    db = ctx["db"]

    async with db() as s:
        started = await ensure_started_or_skip_aborted(s, session_id)
        if not started:
            return {"status": "aborted", "session_id": session_id}

    playwright = None
    browser = None
    context = None
    ws: aiohttp.ClientWebSocketResponse | None = None
    cdp = None
    frame_tasks: set[asyncio.Task[None]] = set()
    event_sender_task: asyncio.Task[None] | None = None
    close_outcome = "aborted"

    try:
        async with db() as s:
            config_json, base_url, graph_id = await fetch_job_inputs(s, session_id)

        payload = _build_payload_from_db(config_json, base_url, session_id, graph_id)
        job = CrawlJob.from_dict(payload, config)
        flow_started = asyncio.Event()
        event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        send_lock = asyncio.Lock()

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=job.headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}",
            ],
        )
        context = await browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            device_scale_factor=1,
            ignore_https_errors=True,
        )
        await _install_dom_recorder(context, session_id, flow_started, event_queue)

        page = await context.new_page()
        page.set_default_timeout(job.timeout_ms)

        async with aiohttp.ClientSession() as http:
            ws = await http.ws_connect(
                _api_internal_ws_url(session_id),
                headers={"x-coverit-internal-token": _internal_token()},
                heartbeat=20,
            )
            event_sender_task = asyncio.create_task(_event_sender(ws, send_lock, event_queue))

            async def navigation_event() -> None:
                try:
                    await _send_navigation(ws, send_lock, page)
                except Exception:
                    logger.debug("Failed to send navigation event for %s", session_id, exc_info=True)

            def on_frame_navigated(frame: Any) -> None:
                if frame == page.main_frame:
                    asyncio.create_task(navigation_event())

            page.on("framenavigated", on_frame_navigated)

            await _send_ws(ws, send_lock, {"type": "session.status", "status": "starting_browser"})
            await page.goto(job.base_url, wait_until="domcontentloaded", timeout=job.timeout_ms)
            try:
                await page.wait_for_load_state(job.page_load_state, timeout=min(job.timeout_ms, 10000))
            except Exception:
                pass

            await _send_navigation(ws, send_lock, page)
            cdp, frame_tasks = await _start_screencast(page, ws, send_lock)
            await _send_ws(
                ws,
                send_lock,
                {
                    "type": "crawler.ready",
                    "sessionId": session_id,
                    "url": page.url,
                    "title": await page.title(),
                    "viewport": {
                        "width": VIEWPORT_WIDTH,
                        "height": VIEWPORT_HEIGHT,
                    },
                    "timestamp": _utc_now(),
                },
            )
            await _send_ws(ws, send_lock, {"type": "session.status", "status": "running"})

            async for ws_message in ws:
                if ws_message.type == aiohttp.WSMsgType.TEXT:
                    try:
                        message = json.loads(ws_message.data)
                    except json.JSONDecodeError:
                        await _send_ws(ws, send_lock, {"type": "error", "message": "Invalid JSON"})
                        continue

                    if not isinstance(message, dict):
                        continue

                    message_type = message.get("type")
                    if message_type == "browser.input":
                        await _handle_browser_input(page, message)
                    elif message_type == "flow.start":
                        flow_started.set()
                        await _send_ws(
                            ws,
                            send_lock,
                            {
                                "type": "flow.started",
                                "sessionId": session_id,
                                "pageUrl": page.url,
                                "title": await page.title(),
                                "timestamp": _utc_now(),
                            },
                        )
                    elif message_type == "session.disconnect":
                        reason = str(message.get("reason") or "")
                        close_outcome = "aborted" if reason == "frontend_disconnected_before_ready" else "completed"
                        break
                elif ws_message.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                    break

            async with db() as s:
                if close_outcome == "completed":
                    await mark_completed_if_running(s, session_id, 0, 0)
                else:
                    await mark_aborted_if_active(s, session_id)

            await _send_ws(ws, send_lock, {"type": "session.closed", "status": close_outcome})
            return {"status": close_outcome, "session_id": session_id}

    except asyncio.CancelledError:
        async with db() as s:
            await mark_finished_at_if_aborted(s, session_id)
        raise

    except Exception as exc:
        message = str(exc)
        async with db() as s:
            updated = await mark_failed_if_running(s, session_id, message)
            if not updated:
                await mark_finished_at_if_aborted(s, session_id)
        if ws is not None and not ws.closed:
            try:
                await _send_ws(ws, asyncio.Lock(), {"type": "error", "message": message})
                await _send_ws(ws, asyncio.Lock(), {"type": "session.closed", "status": "failed"})
            except Exception:
                pass
        logger.error("Manual recording session %s failed: %s", session_id, message, exc_info=True)
        raise

    finally:
        if event_sender_task is not None:
            event_sender_task.cancel()
            await asyncio.gather(event_sender_task, return_exceptions=True)

        await _stop_screencast(cdp, frame_tasks)

        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                pass

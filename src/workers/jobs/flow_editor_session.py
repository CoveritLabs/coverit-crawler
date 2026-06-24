from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any
from pathlib import Path

import aiohttp
from playwright.async_api import async_playwright

from src.config import config
from src.crawler.session.sequence_builders import sequence_description
from src.db.repositories.test_flows import fetch_flow_editor_inputs
from src.models import CrawlAction, CrawlJob
from src.workers.jobs.crawl_session import _build_payload_from_db
from src.workers.jobs.manual_record_session import (
    STATE_HASH_SCRIPT,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
    _internal_token,
    _send_ws,
    _start_screencast,
    _stop_screencast,
    _utc_now,
    _wait_for_page_settle,
)


logger = logging.getLogger(__name__)

SRC_DIR = Path(__file__).resolve().parents[2]
INSPECT_ELEMENT_SCRIPT = (
    SRC_DIR / "crawler" / "session" / "manual_crawl" / "inspect_element.js"
).read_text(encoding="utf-8")


def _api_internal_ws_url(editor_session_id: str) -> str:
    value = os.getenv("COVERIT_API_INTERNAL_WS_URL") or os.getenv("COVERIT_API_INTERNAL_URL")
    if not value:
        raise ValueError("COVERIT_API_INTERNAL_URL is required")

    base = value.rstrip("/")
    if base.startswith("http://"):
        base = f"ws://{base[7:]}"
    elif base.startswith("https://"):
        base = f"wss://{base[8:]}"

    return f"{base}/internal/ws/flow-editors/{editor_session_id}"


def _json_value(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def _transition_actions(raw_transition: dict[str, Any]) -> list[CrawlAction]:
    raw_actions = _json_value(raw_transition.get("value"))
    actions: list[CrawlAction] = []
    if isinstance(raw_actions, list):
        for raw in raw_actions:
            if not isinstance(raw, dict):
                continue
            action_type = str(raw.get("t") or raw.get("type") or raw.get("action_type") or "")
            selector = str(raw.get("s") or raw.get("selector") or "")
            value = raw.get("v") if raw.get("v") is not None else raw.get("value")
            description = str(raw.get("d") or raw.get("description") or action_type)
            if action_type:
                actions.append(
                    CrawlAction(
                        action_type=action_type,
                        selector=selector,
                        value="" if value is None else str(value),
                        description=description,
                    )
                )

    if actions:
        return actions

    action_type = str(raw_transition.get("action_type") or "")
    selector = str(raw_transition.get("selector") or "")
    if not action_type:
        return []
    return [
        CrawlAction(
            action_type=action_type,
            selector=selector,
            value="",
            description=str(raw_transition.get("action_description") or action_type),
        )
    ]


async def _execute_editor_action(page: Any, action: CrawlAction, job: CrawlJob) -> None:
    action_type = str(action.action_type or "")
    selector = str(action.selector or "")
    value = str(action.value or "")

    if action_type == "click":
        if not selector:
            raise RuntimeError("Cannot replay click without a selector")
        await page.click(selector, timeout=job.timeout_ms)
    elif action_type in {"type", "fill"}:
        if selector:
            await page.fill(selector, value, timeout=job.timeout_ms)
        else:
            await page.keyboard.insert_text(value)
    elif action_type == "select":
        if not selector:
            raise RuntimeError("Cannot replay select without a selector")
        await page.select_option(selector, value, timeout=job.timeout_ms)
    elif action_type == "press":
        if selector:
            await page.press(selector, value, timeout=job.timeout_ms)
        else:
            await page.keyboard.press(value)
    elif action_type == "navigate":
        target_url = value or selector
        if target_url:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=job.timeout_ms)
    elif action_type == "hover":
        if selector:
            await page.hover(selector, timeout=job.timeout_ms)
    else:
        raise RuntimeError(f"Cannot replay unsupported action type: {action_type}")

    await _wait_for_page_settle(page, job)


async def _inspect_at(page: Any, x: float, y: float) -> dict[str, Any] | None:
    state_hash = ""
    try:
        from src.browser.state import StateManager

        semantic = await page.evaluate(STATE_HASH_SCRIPT)
        state_hash = StateManager.hash_content(str(semantic))
    except Exception:
        state_hash = ""

    return await page.evaluate(
        INSPECT_ELEMENT_SCRIPT,
        {
            "x": round(float(x or 0)),
            "y": round(float(y or 0)),
            "stateHash": state_hash,
        },
    )


def _transition_index(transitions: list[dict[str, Any]], transition_id: str) -> int:
    for index, transition in enumerate(transitions):
        if str(transition.get("transition_id") or "") == transition_id:
            return index
    raise RuntimeError("Selected transition is not part of this TestFlow")


def _replay_count_for_position(transitions: list[dict[str, Any]], position: dict[str, Any]) -> int:
    transition_id = str(position.get("transitionId") or position.get("transition_id") or "")
    edge = str(position.get("edge") or "before")
    index = _transition_index(transitions, transition_id)
    return index if edge == "before" else index + 1


async def flow_editor_session(ctx: dict, editor_session_id: str, flow_id: str) -> dict[str, Any]:
    db = ctx["db"]

    async with db() as s:
        flow = await fetch_flow_editor_inputs(s, flow_id)
    if flow is None:
        raise RuntimeError(f"TestFlow {flow_id} was not found")

    graph_builder = getattr(ctx.get("crawler_worker"), "_graph_builder", None)
    if graph_builder is None:
        raise RuntimeError("crawler graph builder is not available")

    checkpoint_url, checkpoint_storage_state_json, transitions = await graph_builder.get_data_from_flow_query(
        flow["graph_id"],
        flow["checkpoint_hash"],
        flow["transition_refs"],
    )
    if len(transitions) != len(flow["transition_refs"]):
        raise RuntimeError("TestFlow graph data did not resolve completely")

    base_url = checkpoint_url or flow["base_url"]
    payload = _build_payload_from_db(flow["config"], base_url, flow["crawl_session_id"], flow["graph_id"])
    job = CrawlJob.from_dict(payload, config)

    playwright = None
    browser = None
    context = None
    page = None
    ws: aiohttp.ClientWebSocketResponse | None = None
    cdp = None
    frame_tasks: set[asyncio.Task[None]] = set()
    send_lock = asyncio.Lock()

    async def open_position(position: dict[str, Any] | None = None) -> None:
        nonlocal context, page, cdp, frame_tasks

        await _stop_screencast(cdp, frame_tasks)
        cdp = None
        frame_tasks = set()

        if context is not None:
            try:
                await context.close()
            except Exception:
                pass

        context_kwargs: dict[str, Any] = {
            "viewport": {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            "device_scale_factor": 1,
            "ignore_https_errors": True,
        }
        storage_state = _json_value(checkpoint_storage_state_json)
        if storage_state is not None:
            context_kwargs["storage_state"] = storage_state

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()
        page.set_default_timeout(job.timeout_ms)
        await page.goto(base_url or job.base_url, wait_until="domcontentloaded", timeout=job.timeout_ms)
        await _wait_for_page_settle(page, job)

        replay_count = 0 if position is None else _replay_count_for_position(transitions, position)
        for raw_transition in transitions[:replay_count]:
            actions = _transition_actions(raw_transition)
            logger.info(
                "Flow editor replay action session=%s transition=%s actions=%s",
                editor_session_id,
                raw_transition.get("transition_id") or "",
                sequence_description(actions),
            )
            for action in actions:
                await _execute_editor_action(page, action, job)

        cdp, frame_tasks = await _start_screencast(page, ws, send_lock)
        semantic = await page.evaluate(STATE_HASH_SCRIPT)
        from src.browser.state import StateManager

        await _send_ws(
            ws,
            send_lock,
            {
                "type": "position.ready",
                "editorSessionId": editor_session_id,
                "flowId": flow_id,
                "position": position,
                "pageUrl": page.url,
                "title": await page.title(),
                "stateHash": StateManager.hash_content(str(semantic)),
                "viewport": {
                    "width": VIEWPORT_WIDTH,
                    "height": VIEWPORT_HEIGHT,
                },
                "timestamp": _utc_now(),
            },
        )

    try:
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

        async with aiohttp.ClientSession() as http:
            ws = await http.ws_connect(
                _api_internal_ws_url(editor_session_id),
                headers={"x-coverit-internal-token": _internal_token()},
                heartbeat=20,
            )

            await _send_ws(
                ws,
                send_lock,
                {
                    "type": "editor.ready",
                    "editorSessionId": editor_session_id,
                    "flowId": flow_id,
                    "transitionIds": flow["transition_refs"],
                    "timestamp": _utc_now(),
                },
            )
            await open_position(None)

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
                    if message_type == "editor.open_position":
                        position = message.get("position")
                        if not isinstance(position, dict):
                            await _send_ws(ws, send_lock, {"type": "error", "message": "Position is required"})
                            continue
                        try:
                            await open_position(position)
                        except Exception as exc:
                            await _send_ws(ws, send_lock, {"type": "error", "message": str(exc)})
                    elif message_type in {"inspector.hover", "inspector.pick"}:
                        point = message.get("point") if isinstance(message.get("point"), dict) else message
                        try:
                            element = await _inspect_at(page, float(point.get("x") or 0), float(point.get("y") or 0))
                            await _send_ws(
                                ws,
                                send_lock,
                                {
                                    "type": "inspector.hovered"
                                    if message_type == "inspector.hover"
                                    else "inspector.selected",
                                    "element": element,
                                    "timestamp": _utc_now(),
                                },
                            )
                        except Exception as exc:
                            await _send_ws(ws, send_lock, {"type": "error", "message": str(exc)})
                    elif message_type == "viewport.scroll":
                        payload = message.get("scroll") if isinstance(message.get("scroll"), dict) else message
                        await page.mouse.wheel(
                            float(payload.get("deltaX") or 0),
                            float(payload.get("deltaY") or 0),
                        )
                    elif message_type == "session.disconnect":
                        break
                elif ws_message.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                    break

            await _send_ws(ws, send_lock, {"type": "session.closed", "status": "completed"})
            return {"status": "completed", "editor_session_id": editor_session_id, "flow_id": flow_id}

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if ws is not None and not ws.closed:
            try:
                await _send_ws(ws, send_lock, {"type": "error", "message": str(exc)})
                await _send_ws(ws, send_lock, {"type": "session.closed", "status": "failed"})
            except Exception:
                pass
        logger.error("Flow editor session %s failed: %s", editor_session_id, exc, exc_info=True)
        raise
    finally:
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

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.db.repositories.crawl_sessions import (
    fetch_job_inputs,
    get_session_status,
    mark_completed_if_running,
    mark_failed_if_running,
    mark_finished_at_if_aborted,
)
from src.db.services.crawl_sessions import ensure_started_or_skip_aborted
from src.models import CrawlJob
from src.queue import clear_cancel, crawl_stream_config, is_cancelled

logger = logging.getLogger(__name__)


def _pick(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source:
            return source.get(key)
    return None


def _build_payload_from_db(config_json: dict[str, Any], base_url: str, session_id: str) -> dict[str, Any]:
    crawler_settings = config_json.get("crawlerSettings")
    if not isinstance(crawler_settings, dict):
        crawler_settings = {}

    settings = {
        "headless": _pick(crawler_settings, "headless"),
        "timeout_ms": _pick(crawler_settings, "timeout_ms", "timeoutMs"),
        "max_states": _pick(crawler_settings, "max_states", "maxStates"),
        "max_transitions": _pick(crawler_settings, "max_transitions", "maxTransitions"),
        "max_elements_per_state": _pick(crawler_settings, "max_elements_per_state", "maxElementsPerState"),
        "max_select_options_per_element": _pick(
            crawler_settings,
            "max_select_options_per_element",
            "maxSelectOptionsPerElement",
        ),
        "max_action_repeats_per_url": _pick(crawler_settings, "max_action_repeats_per_url", "maxActionRepeatsPerUrl"),
        "action_retry_count": _pick(crawler_settings, "action_retry_count", "actionRetryCount"),
        "replay_retry_count": _pick(crawler_settings, "replay_retry_count", "replayRetryCount"),
        "popup_timeout_ms": _pick(crawler_settings, "popup_timeout_ms", "popupTimeoutMs"),
        "dom_quiet_ms": _pick(crawler_settings, "dom_quiet_ms", "domQuietMs"),
        "dom_settle_timeout_ms": _pick(crawler_settings, "dom_settle_timeout_ms", "domSettleTimeoutMs"),
        "use_dom_quiescence": _pick(crawler_settings, "use_dom_quiescence", "useDomQuiescence"),
        "page_load_state": _pick(crawler_settings, "page_load_state", "pageLoadState"),
        "click_non_http_links": _pick(crawler_settings, "click_non_http_links", "clickNonHttpLinks"),
        "defer_destructive_actions": _pick(crawler_settings, "defer_destructive_actions", "deferDestructiveActions"),
        "destructive_keywords": (
            ",".join(_pick(crawler_settings, "destructive_keywords", "destructiveKeywords"))
            if isinstance(_pick(crawler_settings, "destructive_keywords", "destructiveKeywords"), list)
            else _pick(crawler_settings, "destructive_keywords", "destructiveKeywords")
        ),
    }

    return {
        "base_url": base_url,
        "session_id": session_id,
        "settings": settings,
        "input_defaults": config_json.get("inputDefaults"),
    }


async def crawl_session(ctx: dict, session_id: str) -> dict[str, Any]:
    redis = ctx.get("redis")
    db = ctx["db"]
    worker = ctx["crawler_worker"]

    stream_cfg = crawl_stream_config()

    if redis is not None and await is_cancelled(redis, stream_cfg, session_id):
        await clear_cancel(redis, stream_cfg, session_id)
        async with db() as s:
            await mark_finished_at_if_aborted(s, session_id)
        return {"status": "cancelled", "session_id": session_id}

    async with db() as s:
        started = await ensure_started_or_skip_aborted(s, session_id)
        if not started:
            return {"status": "aborted", "session_id": session_id}

        config_json, base_url = await fetch_job_inputs(s, session_id)

    payload = _build_payload_from_db(config_json, base_url, session_id)
    job = CrawlJob.from_dict(payload, worker._settings)

    abort_event = asyncio.Event()
    run_permission = asyncio.Event()
    run_permission.set()

    async def abort_poller() -> None:
        while True:
            await asyncio.sleep(1)
            async with db() as poll_s:
                current = await get_session_status(poll_s, session_id)

            if current == "ABORTED":
                abort_event.set()
                return

            if current == "PAUSED":
                run_permission.clear()
            else:
                run_permission.set()

    crawl_task = asyncio.create_task(worker.process(job, run_permission=run_permission))
    poll_task = asyncio.create_task(abort_poller())

    try:
        while True:
            done, _ = await asyncio.wait(
                {crawl_task, poll_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if poll_task in done and abort_event.is_set():
                crawl_task.cancel()
                break
            if crawl_task in done:
                break

        if abort_event.is_set():
            try:
                await crawl_task
            except asyncio.CancelledError:
                pass
            async with db() as s:
                await mark_finished_at_if_aborted(s, session_id)
            return {"status": "aborted", "session_id": session_id}

        state_count, transition_count = await crawl_task
        async with db() as s:
            updated = await mark_completed_if_running(s, session_id, state_count, transition_count)
            if not updated:
                await mark_finished_at_if_aborted(s, session_id)

        return {
            "status": "completed",
            "session_id": session_id,
            "state_count": state_count,
            "transition_count": transition_count,
        }

    except asyncio.CancelledError:
        async with db() as s:
            await mark_finished_at_if_aborted(s, session_id)
        raise

    except Exception as e:
        message = str(e)
        async with db() as s:
            updated = await mark_failed_if_running(s, session_id, message)
            if not updated:
                await mark_finished_at_if_aborted(s, session_id)
        logger.error("Session %s failed: %s", session_id, message, exc_info=True)
        raise

    finally:
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

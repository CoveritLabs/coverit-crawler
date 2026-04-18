import asyncio
import logging
import os
import socket
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker
from ..config import config

from ..db.database import create_engine, create_sessionmaker
from ..db.crawl_sessions import (
    fetch_job_inputs,
    get_session_status,
    mark_completed_if_running,
    mark_failed_if_running,
    mark_finished_at_if_aborted,
    mark_queued_running,
)
from ..queue.crawl_stream import (
    ack_and_delete,
    clear_cancel,
    crawl_stream_config,
    ensure_consumer_group,
    is_cancelled,
    parse_session_id,
)
from .crawler_worker import CrawlJob, CrawlerWorker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _build_payload_from_db(config_json: dict[str, Any], base_url: str, session_id: str) -> dict[str, Any]:
    crawler_settings = config_json.get("crawlerSettings")
    if not isinstance(crawler_settings, dict):
        crawler_settings = {}

    settings = {
        "headless": crawler_settings.get("headless"),
        "timeout_ms": crawler_settings.get("timeout_ms"),
        "max_states": crawler_settings.get("maxStates"),
        "max_transitions": crawler_settings.get("max_transitions"),
        "max_elements_per_state": crawler_settings.get("max_elements_per_state"),
        "max_select_options_per_element": crawler_settings.get("max_select_options_per_element"),
        "max_action_repeats_per_url": crawler_settings.get("max_action_repeats_per_url"),
        "action_retry_count": crawler_settings.get("action_retry_count"),
        "replay_retry_count": crawler_settings.get("replay_retry_count"),
        "popup_timeout_ms": crawler_settings.get("popup_timeout_ms"),
        "dom_quiet_ms": crawler_settings.get("dom_quiet_ms"),
        "dom_settle_timeout_ms": crawler_settings.get("dom_settle_timeout_ms"),
        "use_dom_quiescence": crawler_settings.get("use_dom_quiescence"),
        "page_load_state": crawler_settings.get("page_load_state"),
        "click_non_http_links": crawler_settings.get("click_non_http_links"),
        "defer_destructive_actions": crawler_settings.get("defer_destructive_actions"),
        "destructive_keywords": (
            ",".join(crawler_settings.get("destructive_keywords"))
            if isinstance(crawler_settings.get("destructive_keywords"), list)
            else crawler_settings.get("destructive_keywords")
        ),
    }

    return {
        "base_url": base_url,
        "session_id": session_id,
        "settings": settings,
        "input_defaults": config_json.get("inputDefaults"),
    }


async def _process_session(worker: CrawlerWorker, db: async_sessionmaker, session_id: str) -> None:
    async with db() as s:
        status = await get_session_status(s, session_id)
        if status == "ABORTED":
            await mark_finished_at_if_aborted(s, session_id)
            logger.info("Session %s aborted before start; skipping", session_id)
            return

        started = await mark_queued_running(s, session_id)
        if not started:
            status = await get_session_status(s, session_id)
            if status == "ABORTED":
                await mark_finished_at_if_aborted(s, session_id)
                logger.info("Session %s aborted before start; skipping", session_id)
                return
            raise RuntimeError(f"Cannot start session {session_id} with status {status}")

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
            done, _pending = await asyncio.wait(
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
            return

        state_count, transition_count = await crawl_task

        async with db() as s:
            updated = await mark_completed_if_running(s, session_id, state_count, transition_count)
            if not updated:
                await mark_finished_at_if_aborted(s, session_id)

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
        raise

    finally:
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


async def main() -> int:

    redis_url = os.getenv("REDIS_URL")
    db_url = os.getenv("DATABASE_URL")

    consumer_name = f"{socket.gethostname()}-{os.getpid()}"
    redis = Redis.from_url(redis_url, decode_responses=False)
    engine = create_engine(db_url)
    db = create_sessionmaker(engine)

    worker = CrawlerWorker(config)
    await worker.start()

    stream_cfg = crawl_stream_config()

    try:
        await ensure_consumer_group(redis, stream_cfg)

        logger.info("Crawler queue consumer started (%s)", consumer_name)

        while True:
            resp = await redis.xreadgroup(
                groupname=stream_cfg.group_name,
                consumername=consumer_name,
                streams={stream_cfg.stream_key: ">"},
                count=1,
                block=5000,
            )
            if not resp:
                continue

            for _stream, messages in resp:
                for message_id, fields in messages:
                    try:
                        session_id = parse_session_id(fields)
                        if await is_cancelled(redis, stream_cfg, session_id):
                            await clear_cancel(redis, stream_cfg, session_id)
                            async with db() as s:
                                await mark_finished_at_if_aborted(s, session_id)
                            logger.info("Session %s cancelled while queued; acking", session_id)
                        else:
                            await _process_session(worker, db, session_id)

                        await ack_and_delete(redis, stream_cfg, message_id)

                    except Exception as e:
                        logger.error("Job %s failed: %s", message_id, e, exc_info=True)
                        try:
                            await ack_and_delete(redis, stream_cfg, message_id)
                        except Exception:
                            pass

    finally:
        await worker.stop()
        await engine.dispose()
        await redis.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

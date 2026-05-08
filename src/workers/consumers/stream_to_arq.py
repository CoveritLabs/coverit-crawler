from __future__ import annotations

import asyncio
import logging
import os
import socket

from arq.connections import create_pool

from src import config
from src.db import create_engine, create_sessionmaker, mark_finished_at_if_aborted
from src.queue import (
    ack_and_delete,
    clear_cancel,
    crawl_stream_config,
    ensure_consumer_group,
    is_cancelled,
    parse_session_id,
)
from src.workers.main import _redis_settings_from_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> int:
    redis_url = config.REDIS_URL
    db_url = config.DATABASE_URL

    if not redis_url:
        raise ValueError("REDIS_URL is required")
    if not db_url:
        raise ValueError("DATABASE_URL is required")

    consumer_name = f"{socket.gethostname()}-{os.getpid()}"

    redis = await create_pool(_redis_settings_from_url(redis_url))
    engine = create_engine(db_url)
    db = create_sessionmaker(engine)
    stream_cfg = crawl_stream_config()

    try:
        await ensure_consumer_group(redis, stream_cfg)
        logger.info("Stream→ARQ consumer started (%s)", consumer_name)

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

            for _, messages in resp:
                for message_id, fields in messages:
                    session_id = None
                    try:
                        session_id = parse_session_id(fields)

                        if await is_cancelled(redis, stream_cfg, session_id):
                            await clear_cancel(redis, stream_cfg, session_id)
                            async with db() as s:
                                await mark_finished_at_if_aborted(s, session_id)
                            await ack_and_delete(redis, stream_cfg, message_id)
                            continue

                        await redis.enqueue_job(
                            "crawl_session",
                            session_id,
                            _job_id=session_id,
                        )
                        await ack_and_delete(redis, stream_cfg, message_id)

                    except Exception as e:
                        logger.error(
                            "Stream message %s (session %s) failed: %s",
                            message_id,
                            session_id,
                            e,
                            exc_info=True,
                        )

    finally:
        await engine.dispose()
        await redis.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

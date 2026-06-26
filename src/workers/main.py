from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from arq.connections import RedisSettings
from arq.worker import run_worker

from src import config
from src.db import create_engine, create_sessionmaker
from src.workers.crawler_worker import CrawlerWorker
from src.workers.jobs.crawl_session import crawl_session
from src.workers.logging_config import configure_worker_logging

configure_worker_logging("crawler-worker")


def arq_job_serializer(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), default=str).encode("utf-8")


def arq_job_deserializer(value: bytes) -> Any:
    return json.loads(value.decode("utf-8"))


def _redis_settings_from_url(url: str) -> RedisSettings:
    parsed = urlparse(url)

    if parsed.scheme not in {"redis", "rediss"}:
        raise ValueError("REDIS_URL must start with redis:// or rediss://")

    path = (parsed.path or "/").lstrip("/")
    database = int(path) if path else 0

    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=int(parsed.port or 6379),
        database=database,
        username=parsed.username,
        password=parsed.password,
        ssl=parsed.scheme == "rediss",
    )


def _crawler_job_timeout_seconds() -> int:
    return max(
        config.CRAWLER_JOB_TIMEOUT_SECONDS,
        config.CRAWLER_JOB_SLICE_SECONDS + 120,
    )


async def startup(ctx: dict) -> None:
    db_url = config.DATABASE_URL
    if not db_url:
        raise ValueError("DATABASE_URL is required")

    engine = create_engine(db_url)
    db = create_sessionmaker(engine)

    crawler_worker = CrawlerWorker(config)
    await crawler_worker.start()

    ctx["engine"] = engine
    ctx["db"] = db
    ctx["crawler_worker"] = crawler_worker
    ctx["run_flows_inline"] = True


async def shutdown(ctx: dict) -> None:
    crawler_worker = ctx.get("crawler_worker")
    if crawler_worker is not None:
        await crawler_worker.stop()

    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


class WorkerSettings:
    redis_settings = _redis_settings_from_url(config.REDIS_URL)
    queue_name = config.ARQ_QUEUE_NAME
    functions = [crawl_session]
    on_startup = startup
    on_shutdown = shutdown
    cron_jobs = []
    max_jobs = config.CRAWLER_MAX_JOBS
    job_timeout = _crawler_job_timeout_seconds()
    keep_result = 0
    allow_abort_jobs = True
    job_serializer = arq_job_serializer
    job_deserializer = arq_job_deserializer
    expires_extra_ms = config.ARQ_JOB_EXPIRES_MS


if __name__ == "__main__":
    run_worker(WorkerSettings)

from __future__ import annotations

from urllib.parse import urlparse

from arq.connections import RedisSettings
from arq.worker import WorkerSettings as ArqWorkerSettings

from src import config
from src.db import create_engine, create_sessionmaker
from src.workers.crawler_worker import CrawlerWorker
from src.workers.flow_worker import generate_flows_for_session
from src.workers.jobs.crawl_session import crawl_session


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


async def shutdown(ctx: dict) -> None:
    crawler_worker = ctx.get("crawler_worker")
    if crawler_worker is not None:
        await crawler_worker.stop()

    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


class WorkerSettings(ArqWorkerSettings):
    redis_settings = _redis_settings_from_url(config.REDIS_URL or "redis://localhost:6379/0")
    functions = [crawl_session,generate_flows_for_session]
    on_startup = startup
    on_shutdown = shutdown
    cron_jobs = []

    max_jobs = 10
    job_timeout = 60 * 30
    keep_result = 0

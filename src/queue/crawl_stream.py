from dataclasses import dataclass
from typing import Any, Mapping

from redis.asyncio import Redis


@dataclass(frozen=True)
class CrawlStreamConfig:
    stream_key: str
    group_name: str
    cancel_prefix: str


def crawl_stream_config() -> CrawlStreamConfig:
    return CrawlStreamConfig(
        stream_key="crawl:jobs",
        group_name="CRAWL_GROUP",
        cancel_prefix="crawl:cancelled:",
    )


async def ensure_consumer_group(redis: Redis, cfg: CrawlStreamConfig) -> None:
    try:
        await redis.xgroup_create(cfg.stream_key, cfg.group_name, id="0", mkstream=True)
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            raise


def parse_session_id(fields: Mapping[bytes, Any]) -> str:
    raw = fields.get(b"sessionId") or fields.get(b"session_id")
    if raw is None:
        raise ValueError("Missing sessionId in job")
    if isinstance(raw, (bytes, bytearray)):
        return raw.decode("utf-8")
    return str(raw)


def cancel_key(cfg: CrawlStreamConfig, session_id: str) -> str:
    return f"{cfg.cancel_prefix}{session_id}"


async def is_cancelled(redis: Redis, cfg: CrawlStreamConfig, session_id: str) -> bool:
    return await redis.get(cancel_key(cfg, session_id)) is not None


async def clear_cancel(redis: Redis, cfg: CrawlStreamConfig, session_id: str) -> None:
    await redis.delete(cancel_key(cfg, session_id))


async def ack_and_delete(redis: Redis, cfg: CrawlStreamConfig, message_id: bytes) -> None:
    await redis.xack(cfg.stream_key, cfg.group_name, message_id)
    await redis.xdel(cfg.stream_key, message_id)

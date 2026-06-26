from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import aiohttp
import asyncpg
from dotenv import load_dotenv
from redis.asyncio import Redis


def _load_env() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    load_dotenv(Path.cwd() / ".env", override=False)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _payload(function_name: str, args: list[Any]) -> str:
    return json.dumps({"t": None, "f": function_name, "a": args, "k": {}, "et": _now_ms()}, separators=(",", ":"))


async def _enqueue(redis: Redis, queue_name: str, session_id: str, expires_ms: int) -> None:
    script = """
if redis.call("exists", KEYS[1]) == 1 or redis.call("exists", KEYS[2]) == 1 then
  return nil
end
redis.call("psetex", KEYS[1], ARGV[1], ARGV[2])
redis.call("zadd", KEYS[3], ARGV[3], ARGV[4])
return ARGV[4]
"""
    await redis.eval(
        script,
        3,
        f"arq:job:{session_id}",
        f"arq:result:{session_id}",
        queue_name,
        str(expires_ms),
        _payload("crawl_session", [session_id]),
        str(_now_ms()),
        session_id,
    )


async def _status(conn: asyncpg.Connection, session_id: str) -> str:
    row = await conn.fetchrow(
        """
        select status, state_count, transition_count, error
        from crawl_sessions
        where crawl_session_id = $1::uuid
        """,
        session_id,
    )
    if row is None:
        return "missing"
    err = f" error={row['error']}" if row["error"] else ""
    return f"{row['status']} states={row['state_count']} transitions={row['transition_count']}{err}"


async def _target(conn: asyncpg.Connection, session_id: str) -> str:
    row = await conn.fetchrow(
        """
        select
          cs.status,
          cs.app_version_id,
          coalesce(cs.base_url_snapshot, ta.base_url) as base_url
        from crawl_sessions cs
        left join target_application_versions tav on tav.id = cs.app_version_id
        left join target_applications ta on ta.id = tav.target_application_id
        where cs.crawl_session_id = $1::uuid
        """,
        session_id,
    )
    if row is None:
        return "session=missing"
    return f"url={row['base_url']} graph_id={row['app_version_id']} status={row['status']}"


async def _redis_state(redis: Redis, queue_name: str, session_id: str) -> str:
    queued = await redis.zscore(queue_name, session_id)
    has_job = await redis.exists(f"arq:job:{session_id}")
    in_progress = await redis.exists(f"arq:in-progress:{session_id}")
    has_result = await redis.exists(f"arq:result:{session_id}")
    return f"queued={bool(queued)} job={bool(has_job)} running={bool(in_progress)} result={bool(has_result)}"


async def _call_api(args: argparse.Namespace) -> None:
    headers = {}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    async with aiohttp.ClientSession(headers=headers) as http:
        async with http.request(args.method, args.start_url) as resp:
            body = await resp.text()
            print(f"api {resp.status} {body}")
            if resp.status >= 400:
                raise SystemExit(1)


async def _mark_queued(conn: asyncpg.Connection, session_id: str) -> None:
    await conn.execute(
        """
        update crawl_sessions
        set status = 'QUEUED', finished_at = null, error = null
        where crawl_session_id = $1::uuid
        and status in ('NEW', 'FAILED', 'ABORTED')
        """,
        session_id,
    )


async def main() -> int:
    _load_env()

    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    parser.add_argument("--queue-name", default=os.getenv("CRAWL_ARQ_QUEUE_NAME", "arq:queue"))
    parser.add_argument("--expires-ms", type=int, default=int(os.getenv("CRAWL_ARQ_EXPIRES_MS", "86400000")))
    parser.add_argument("--session-id")
    parser.add_argument("--start-url")
    parser.add_argument("--method", default="PUT")
    parser.add_argument("--token", default=os.getenv("COVERIT_API_TOKEN"))
    parser.add_argument("--direct-enqueue", action="store_true")
    parser.add_argument("--watch-seconds", type=int, default=120)
    parser.add_argument("--poll-seconds", type=float, default=2)
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")

    redis = Redis.from_url(args.redis_url, decode_responses=True)
    conn = await asyncpg.connect(args.database_url)
    try:
        if args.session_id:
            print(f"target {await _target(conn, args.session_id)}")

        if args.start_url:
            await _call_api(args)

        if args.direct_enqueue:
            if not args.session_id:
                raise SystemExit("--session-id is required with --direct-enqueue")
            await _mark_queued(conn, args.session_id)
            await _enqueue(redis, args.queue_name, args.session_id, args.expires_ms)
            print(f"enqueued {args.session_id}")

        if args.session_id:
            deadline = time.monotonic() + args.watch_seconds
            while True:
                db_state = await _status(conn, args.session_id)
                redis_state = await _redis_state(redis, args.queue_name, args.session_id)
                print(f"{args.session_id} db={db_state} redis={redis_state}")
                if db_state.startswith(("COMPLETED", "FAILED", "ABORTED")):
                    break
                if time.monotonic() >= deadline:
                    break
                await asyncio.sleep(args.poll_seconds)
    finally:
        await conn.close()
        await redis.aclose()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

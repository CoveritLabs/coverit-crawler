import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from ..config import Config, config
from ..crawler.session import CrawlSession
from ..graph.builder import Neo4jGraphBuilder


logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_input_config_path() -> Optional[str]:
    candidate = _repo_root() / "input_defaults.json"
    return str(candidate) if candidate.exists() else None


def _resolve_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    p = Path(path)
    if p.is_absolute():
        return str(p)
    return str((_repo_root() / p).resolve())


def _coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        return int(s)
    return default


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in {"true", "1", "yes", "y", "on"}:
            return True
        if s in {"false", "0", "no", "n", "off"}:
            return False
    return default


@dataclass(frozen=True)
class CrawlJob:
    base_url: str
    session_id: str
    max_states: int
    max_transitions: int
    headless: bool
    config_path: Optional[str] = None

    @staticmethod
    def from_dict(payload: dict[str, Any], settings: Config) -> "CrawlJob":
        base_url = str(payload.get("base_url") or "").strip()
        if not base_url:
            raise ValueError("base_url is required")

        session_id = str(payload.get("session_id") or "").strip() or str(uuid4())
        max_states = _coerce_int(payload.get("max_states"), int(settings.MAX_STATES))
        max_transitions = _coerce_int(payload.get("max_transitions"), 500)
        headless = _coerce_bool(payload.get("headless"), bool(settings.HEADLESS))
        config_path = _resolve_path(str(payload.get("config_path") or "").strip())
        if not config_path:
            config_path = _default_input_config_path()

        return CrawlJob(
            base_url=base_url,
            session_id=session_id,
            max_states=max_states,
            max_transitions=max_transitions,
            headless=headless,
            config_path=config_path,
        )


class CrawlerWorker:
    def __init__(self, settings: Config = config):
        self._settings = settings
        self._graph_builder = Neo4jGraphBuilder(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self._graph_builder.connect()
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        await self._graph_builder.disconnect()
        self._started = False

    async def process(self, job: CrawlJob) -> None:
        session = CrawlSession(
            base_url=job.base_url,
            graph_builder=self._graph_builder,
            config_path=job.config_path,
            session_id=job.session_id,
            headless=job.headless,
            settings=self._settings,
        )
        await session.run_crawl(max_states=job.max_states, max_transitions=job.max_transitions)


async def _run_once(args: argparse.Namespace, settings: Config) -> int:
    worker = CrawlerWorker(settings)
    await worker.start()
    try:
        payload: dict[str, Any] = {
            "base_url": args.base_url,
            "session_id": args.session_id,
            "max_states": args.max_states,
            "max_transitions": args.max_transitions,
            "headless": args.headless,
            "config_path": args.config_path,
        }
        job = CrawlJob.from_dict(payload, settings)
        await worker.process(job)
        print(json.dumps({"status": "ok", "session_id": job.session_id}), flush=True)
        return 0
    finally:
        await worker.stop()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", type=str)
    parser.add_argument("--session-id", type=str)
    parser.add_argument("--max-states", type=int)
    parser.add_argument("--max-transitions", type=int)
    parser.add_argument("--config-path", type=str)
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=None)
    return parser


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def main() -> int:
    _configure_logging()
    args = _build_parser().parse_args()

    settings = config

    if not args.base_url:
        raise ValueError("--base-url is required")

    return await _run_once(args, settings)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
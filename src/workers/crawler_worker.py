import argparse
import asyncio
import json
import logging
import sys
from copy import copy
from typing import Optional
from .crawl_job import CrawlJob

from ..config import Config, config
from ..crawler.session import CrawlSession
from ..graph.builder import Neo4jGraphBuilder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _job_settings(base: Config, job: CrawlJob) -> Config:
    overridden = copy(base)
    overridden.HEADLESS = job.headless
    overridden.TIMEOUT_MS = job.timeout_ms
    overridden.MAX_STATES = job.max_states
    overridden.MAX_TRANSITIONS = job.max_transitions
    overridden.MAX_ELEMENTS_PER_STATE = job.max_elements_per_state
    overridden.MAX_SELECT_OPTIONS_PER_ELEMENT = job.max_select_options_per_element
    overridden.MAX_ACTION_REPEATS_PER_URL = job.max_action_repeats_per_url
    overridden.ACTION_RETRY_COUNT = job.action_retry_count
    overridden.REPLAY_RETRY_COUNT = job.replay_retry_count
    overridden.POPUP_TIMEOUT_MS = job.popup_timeout_ms
    overridden.DOM_QUIET_MS = job.dom_quiet_ms
    overridden.DOM_SETTLE_TIMEOUT_MS = job.dom_settle_timeout_ms
    overridden.USE_DOM_QUIESCENCE = job.use_dom_quiescence
    overridden.PAGE_LOAD_STATE = job.page_load_state
    overridden.CLICK_NON_HTTP_LINKS = job.click_non_http_links
    overridden.DEFER_DESTRUCTIVE_ACTIONS = job.defer_destructive_actions
    overridden.DESTRUCTIVE_KEYWORDS = job.destructive_keywords
    return overridden


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

    async def process(self, job: CrawlJob, run_permission: Optional[asyncio.Event] = None) -> tuple[int, int]:
        job_settings = _job_settings(self._settings, job)
        session = CrawlSession(
            base_url=job.base_url,
            graph_builder=self._graph_builder,
            config_path=job.input_defaults_path,
            session_id=job.session_id,
            headless=job.headless,
            max_states=job.max_states,
            max_transitions=job.max_transitions,
            timeout_ms=job.timeout_ms,
            input_defaults=job.input_defaults,
            settings=job_settings,
            run_permission=run_permission,
        )
        await session.run_crawl()
        return session.state_count, session.transition_count


async def _run_once(args: argparse.Namespace, settings: Config) -> int:
    worker = CrawlerWorker(settings)
    await worker.start()
    try:
        raw = sys.stdin.read() if args.payload_stdin else args.payload_json
        if not raw or not str(raw).strip():
            raise ValueError("payload is required")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        job = CrawlJob.from_dict(payload, settings)
        state_count, transition_count = await worker.process(job)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "session_id": job.session_id,
                    "state_count": state_count,
                    "transition_count": transition_count,
                }
            ),
            flush=True,
        )
        return 0
    finally:
        await worker.stop()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-stdin", action="store_true")
    parser.add_argument("--payload-json", type=str)
    return parser


async def main() -> int:
    args = _build_parser().parse_args()

    settings = config

    if not (args.payload_stdin or args.payload_json):
        raise ValueError("--payload-stdin or --payload-json is required")

    return await _run_once(args, settings)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
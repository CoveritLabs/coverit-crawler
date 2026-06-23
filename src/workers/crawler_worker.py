import argparse
import asyncio
import json
import logging
import sys
from dataclasses import replace
from typing import Optional

from src import Config, config
from src.browser import BrowserRuntime
from src.crawler import CrawlSession
from src.graph import Neo4jGraphBuilder
from src.models import CrawlJob

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _job_settings(base: Config, job: CrawlJob) -> Config:
    return replace(
        base,
        HEADLESS=job.headless,
        TIMEOUT_MS=job.timeout_ms,
        MAX_STATES=job.max_states,
        MAX_TRANSITIONS=job.max_transitions,
        MAX_ELEMENTS_PER_STATE=job.max_elements_per_state,
        MAX_SELECT_OPTIONS_PER_ELEMENT=job.max_select_options_per_element,
        MAX_ACTION_REPEATS_PER_URL=job.max_action_repeats_per_url,
        ACTION_RETRY_COUNT=job.action_retry_count,
        REPLAY_RETRY_COUNT=job.replay_retry_count,
        POPUP_TIMEOUT_MS=job.popup_timeout_ms,
        DOM_QUIET_MS=job.dom_quiet_ms,
        DOM_SETTLE_TIMEOUT_MS=job.dom_settle_timeout_ms,
        USE_DOM_QUIESCENCE=job.use_dom_quiescence,
        PAGE_LOAD_STATE=job.page_load_state,
        CLICK_NON_HTTP_LINKS=job.click_non_http_links,
        DEFER_DESTRUCTIVE_ACTIONS=job.defer_destructive_actions,
        DESTRUCTIVE_KEYWORDS=job.destructive_keywords,
        USE_SEMANTIC_DIVERSITY=job.use_semantic_diversity,
        SEMANTIC_DIVERSITY_THRESHOLD=job.semantic_diversity_threshold,
        SEMANTIC_UNCERTAINTY_MARGIN=job.semantic_uncertainty_margin,
        SEMANTIC_MAX_BANK_SIZE=job.semantic_max_bank_size,
        SEMANTIC_ARTIFACT_DIR=job.semantic_artifact_dir,
    )


class CrawlerWorker:
    def __init__(self, settings: Config = config):
        self._settings = settings
        self._graph_builder = Neo4jGraphBuilder(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        self._browser_runtime = BrowserRuntime(headless=settings.HEADLESS)
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self._graph_builder.connect()
        await self._browser_runtime.start()
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            await self._browser_runtime.stop()
        finally:
            await self._graph_builder.disconnect()
            self._started = False

    async def process(
        self,
        job: CrawlJob,
        run_permission: Optional[asyncio.Event] = None,
        *,
        stop_requested: asyncio.Event | None = None,
        slice_deadline_monotonic: float | None = None,
        initial_state_count: int = 0,
        initial_transition_count: int = 0,
    ) -> tuple[int, int]:
        job_settings = _job_settings(self._settings, job)
        browser_runtime = (
            self._browser_runtime
            if job.headless == self._browser_runtime.headless
            else None
        )
        session = CrawlSession(
            base_url=job.base_url,
            graph_builder=self._graph_builder,
            config_path=job.input_defaults_path,
            session_id=job.graph_id,
            crawl_session_id=job.session_id,
            headless=job.headless,
            max_states=job.max_states,
            max_transitions=job.max_transitions,
            timeout_ms=job.timeout_ms,
            input_defaults=job.input_defaults,
            settings=job_settings,
            browser_runtime=browser_runtime,
            run_permission=run_permission,
            stop_requested=stop_requested,
            slice_deadline_monotonic=slice_deadline_monotonic,
            initial_state_count=initial_state_count,
            initial_transition_count=initial_transition_count,
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

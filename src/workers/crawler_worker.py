import argparse
import asyncio
import json
import logging
import sys
from copy import copy
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


def _coerce_str(value: Any, default: str) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        s = value.strip()
        return s if s else default
    return str(value)


@dataclass(frozen=True)
class CrawlJob:
    base_url: str
    session_id: str
    headless: bool
    timeout_ms: int
    max_states: int
    max_transitions: int
    max_elements_per_state: int
    max_select_options_per_element: int
    max_action_repeats_per_url: int
    action_retry_count: int
    replay_retry_count: int
    popup_timeout_ms: int
    dom_quiet_ms: int
    dom_settle_timeout_ms: int
    use_dom_quiescence: bool
    page_load_state: str
    click_non_http_links: bool
    defer_destructive_actions: bool
    destructive_keywords: str
    input_defaults: Optional[dict[str, Any]] = None
    input_defaults_path: Optional[str] = None

    @staticmethod
    def from_dict(payload: dict[str, Any], settings: Config) -> "CrawlJob":
        nested_settings = payload.get("settings")
        if not isinstance(nested_settings, dict):
            raise ValueError("settings must be an object")

        base_url = str(payload.get("base_url") or "").strip()
        if not base_url:
            raise ValueError("base_url is required")

        session_id = str(payload.get("session_id") or "").strip() or str(uuid4())
        headless = _coerce_bool(nested_settings.get("headless"), bool(getattr(settings, "HEADLESS", True)))
        timeout_ms = _coerce_int(nested_settings.get("timeout_ms"), int(getattr(settings, "TIMEOUT_MS", 3000)))
        max_states = _coerce_int(nested_settings.get("max_states"), int(getattr(settings, "MAX_STATES", 1000)))
        max_transitions = _coerce_int(
            nested_settings.get("max_transitions"),
            int(getattr(settings, "MAX_TRANSITIONS", 5000)),
        )
        max_elements_per_state = _coerce_int(
            nested_settings.get("max_elements_per_state"),
            int(getattr(settings, "MAX_ELEMENTS_PER_STATE", 30)),
        )
        max_select_options_per_element = _coerce_int(
            nested_settings.get("max_select_options_per_element"),
            int(getattr(settings, "MAX_SELECT_OPTIONS_PER_ELEMENT", 3)),
        )
        max_action_repeats_per_url = _coerce_int(
            nested_settings.get("max_action_repeats_per_url"),
            int(getattr(settings, "MAX_ACTION_REPEATS_PER_URL", 2)),
        )
        action_retry_count = _coerce_int(
            nested_settings.get("action_retry_count"),
            int(getattr(settings, "ACTION_RETRY_COUNT", 1)),
        )
        replay_retry_count = _coerce_int(
            nested_settings.get("replay_retry_count"),
            int(getattr(settings, "REPLAY_RETRY_COUNT", 1)),
        )
        popup_timeout_ms = _coerce_int(
            nested_settings.get("popup_timeout_ms"),
            int(getattr(settings, "POPUP_TIMEOUT_MS", 3000)),
        )
        dom_quiet_ms = _coerce_int(
            nested_settings.get("dom_quiet_ms"),
            int(getattr(settings, "DOM_QUIET_MS", 400)),
        )
        dom_settle_timeout_ms = _coerce_int(
            nested_settings.get("dom_settle_timeout_ms"),
            int(getattr(settings, "DOM_SETTLE_TIMEOUT_MS", 3000)),
        )
        use_dom_quiescence = _coerce_bool(
            nested_settings.get("use_dom_quiescence"),
            bool(getattr(settings, "USE_DOM_QUIESCENCE", True)),
        )
        page_load_state = _coerce_str(
            nested_settings.get("page_load_state"),
            str(getattr(settings, "PAGE_LOAD_STATE", "networkidle")),
        )
        click_non_http_links = _coerce_bool(
            nested_settings.get("click_non_http_links"),
            bool(getattr(settings, "CLICK_NON_HTTP_LINKS", False)),
        )
        defer_destructive_actions = _coerce_bool(
            nested_settings.get("defer_destructive_actions"),
            bool(getattr(settings, "DEFER_DESTRUCTIVE_ACTIONS", True)),
        )
        destructive_keywords = _coerce_str(
            nested_settings.get("destructive_keywords"),
            str(getattr(settings, "DESTRUCTIVE_KEYWORDS", "")),
        )

        input_defaults_path = _default_input_config_path()

        input_defaults = payload.get("input_defaults")
        if not isinstance(input_defaults, dict):
            input_defaults = None

        return CrawlJob(
            base_url=base_url,
            session_id=session_id,
            headless=headless,
            timeout_ms=timeout_ms,
            max_states=max_states,
            max_transitions=max_transitions,
            max_elements_per_state=max_elements_per_state,
            max_select_options_per_element=max_select_options_per_element,
            max_action_repeats_per_url=max_action_repeats_per_url,
            action_retry_count=action_retry_count,
            replay_retry_count=replay_retry_count,
            popup_timeout_ms=popup_timeout_ms,
            dom_quiet_ms=dom_quiet_ms,
            dom_settle_timeout_ms=dom_settle_timeout_ms,
            use_dom_quiescence=use_dom_quiescence,
            page_load_state=page_load_state,
            click_non_http_links=click_non_http_links,
            defer_destructive_actions=defer_destructive_actions,
            destructive_keywords=destructive_keywords,
            input_defaults=input_defaults,
            input_defaults_path=input_defaults_path,
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
            config_path=job.input_defaults_path,
            session_id=job.session_id,
            headless=job.headless,
            max_states=job.max_states,
            max_transitions=job.max_transitions,
            timeout_ms=job.timeout_ms,
            input_defaults=job.input_defaults,
            settings=self._settings,
        )
        await session.run_crawl()


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

        # Ensure per-run overrides apply even when downstream reads from settings.
        overridden = copy(settings)
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
        worker._settings = overridden

        await worker.process(job)
        print(json.dumps({"status": "ok", "session_id": job.session_id}), flush=True)
        return 0
    finally:
        await worker.stop()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-stdin", action="store_true")
    parser.add_argument("--payload-json", type=str)
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

    if not (args.payload_stdin or args.payload_json):
        raise ValueError("--payload-stdin or --payload-json is required")

    return await _run_once(args, settings)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
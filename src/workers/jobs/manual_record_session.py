from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiohttp
from playwright.async_api import async_playwright

from src.browser.state import StateManager
from src.config import config
from src.crawler.fingerprints import action_key_fingerprint, transition_fingerprint
from src.crawler.session.manual_crawl.recording_mapper import map_steps_to_actions
from src.crawler.session.sequence_builders import (
    sequence_description,
    sequence_digest,
    sequence_value_for_graph,
)
from src.db.enums import TestFlowType
from src.db.repositories.crawl_sessions import (
    fetch_job_inputs,
    mark_aborted_if_active,
    mark_completed_if_running,
    mark_failed_if_running,
    mark_finished_at_if_aborted,
)
from src.db.repositories.test_flows import create_test_flow
from src.db.services.crawl_sessions import ensure_started_or_skip_aborted
from src.models import AbstractState, AbstractTransition, CrawlAction, CrawlJob
from src.workers.jobs.crawl_session import _build_payload_from_db

logger = logging.getLogger(__name__)

VIEWPORT_WIDTH = 1365
VIEWPORT_HEIGHT = 768
PENDING_EVENT_FLUSH_SECONDS = 0.25
STATE_MONITOR_INTERVAL_SECONDS = 0.1
TTL_MONITOR_MAX_INTERVAL_SECONDS = 30.0
SRC_DIR = Path(__file__).resolve().parents[2]
DOM_RECORDER_SCRIPT = (
    SRC_DIR / "crawler" / "session" / "manual_crawl" / "action_recorder.js"
).read_text(encoding="utf-8")
STATE_HASH_SCRIPT = (SRC_DIR / "browser" / "js" / "get_state_hash.js").read_text(
    encoding="utf-8"
)
ANNOTATED_PAGE_CONTENT_SCRIPT = (
    SRC_DIR / "browser" / "js" / "get_annotated_page_content.js"
).read_text(encoding="utf-8")
INSPECT_ELEMENT_SCRIPT = (
    SRC_DIR / "crawler" / "session" / "manual_crawl" / "inspect_element.js"
).read_text(encoding="utf-8")

SelectorResolver = Callable[[str, str], Awaitable[bool]]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _api_internal_ws_url(session_id: str) -> str:
    value = os.getenv("COVERIT_API_INTERNAL_WS_URL") or os.getenv("COVERIT_API_INTERNAL_URL")
    if not value:
        raise ValueError("COVERIT_API_INTERNAL_URL is required")

    base = value.rstrip("/")
    if base.startswith("http://"):
        base = f"ws://{base[7:]}"
    elif base.startswith("https://"):
        base = f"wss://{base[8:]}"

    return f"{base}/internal/ws/manual-recordings/{session_id}"


def _api_internal_url(path: str) -> str:
    value = os.getenv("COVERIT_API_INTERNAL_URL")
    if not value:
        raise ValueError("COVERIT_API_INTERNAL_URL is required")
    return f"{value.rstrip('/')}{path}"


def _internal_token() -> str:
    token = os.getenv("INTERNAL_SERVICE_TOKEN", "").strip()
    if not token:
        raise ValueError("INTERNAL_SERVICE_TOKEN is required")
    return token


def _source_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


async def _create_manual_bug_report(payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-coverit-internal-token": _internal_token(),
    }
    async with aiohttp.ClientSession() as http:
        async with http.post(
            _api_internal_url("/internal/reports/manual-bug"),
            data=json.dumps(payload),
            headers=headers,
        ) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"manual bug report creation failed with {response.status}: {text}")
            return json.loads(text) if text else {}


async def _wait_for_page_settle(page: Any, job: CrawlJob) -> None:
    try:
        await page.wait_for_load_state(job.page_load_state, timeout=min(job.timeout_ms, 10000))
    except Exception:
        pass


async def _capture_manual_html(page: Any) -> str:
    try:
        return await page.evaluate(ANNOTATED_PAGE_CONTENT_SCRIPT)
    except Exception:
        return await page.content()


async def _capture_manual_state(page: Any, job: CrawlJob) -> AbstractState:
    await _wait_for_page_settle(page, job)
    semantic = await page.evaluate(STATE_HASH_SCRIPT)
    html = await _capture_manual_html(page)
    url = str(getattr(page, "url", "") or "")
    if url.endswith("?"):
        url = url[:-1]
    return AbstractState(
        state_hash=StateManager.hash_content(str(semantic)),
        url=url,
        title=await page.title(),
        html=html,
        dom_snapshot={"content_length": len(html)},
        metadata={"timestamp": _utc_now()},
    )


def _build_manual_transition(
    *,
    graph_id: str,
    session_id: str,
    source: AbstractState,
    target: AbstractState,
    actions: list[CrawlAction],
    unique_key: str = "",
) -> AbstractTransition:
    primary = actions[-1]
    primary.metadata = dict(primary.metadata or {})
    digest = sequence_digest(actions)
    if unique_key:
        primary.metadata["manual_step_id"] = unique_key
    primary.metadata["sequence_digest"] = digest
    primary.metadata["sequence_len"] = len(actions)
    fp = transition_fingerprint(
        graph_id=graph_id,
        source_state_hash=source.state_hash,
        target_state_hash=target.state_hash,
        action=primary,
    )
    return AbstractTransition(
        graph_id=graph_id,
        session_id=session_id,
        transition_id=fp,
        source_state_hash=source.state_hash,
        target_state_hash=target.state_hash,
        action_type=primary.action_type,
        action_description=sequence_description(actions),
        locator_id=primary.action_id,
        locator_value=primary.selector,
        action_value=sequence_value_for_graph(actions),
        action_fingerprint=fp,
        action_stable_key=action_key_fingerprint(primary),
    )


def _action_has_selector(action: CrawlAction) -> bool:
    return bool(str(action.selector or "").strip())


def _action_is_input_like(action: CrawlAction) -> bool:
    return str(action.action_type or "") in {"type", "select"}


def _action_is_password(action: CrawlAction) -> bool:
    return str((action.metadata or {}).get("type") or "").lower() == "password"


def _display_action_value(action: CrawlAction) -> str:
    return str(action.value or "")


def _display_action(action: CrawlAction) -> CrawlAction:
    return CrawlAction(
        action_id=action.action_id,
        action_type=action.action_type,
        selector=action.selector,
        value=_display_action_value(action),
        description=action.description,
        metadata=dict(action.metadata or {}),
    )


def _input_action_selector(actions: list[CrawlAction]) -> str:
    if not actions:
        return ""

    selectors = {str(action.selector or "").strip() for action in actions}
    if len(selectors) != 1:
        return ""

    selector = next(iter(selectors))
    if not selector:
        return ""
    if not all(_action_is_input_like(action) for action in actions):
        return ""
    return selector


def _focus_click_selector(actions: list[CrawlAction]) -> str:
    if len(actions) != 1:
        return ""
    action = actions[0]
    if str(action.action_type or "") != "click":
        return ""
    return str(action.selector or "").strip()


def _event_action(event: dict[str, Any]) -> str:
    return str(event.get("action") or "")


def _event_is_input_like(event: dict[str, Any]) -> bool:
    return _event_action(event) in {"input", "change"}


def _event_selector(event: dict[str, Any]) -> str:
    candidates: list[str] = []
    raw_candidates = event.get("selectorCandidates") or event.get("selector_candidates") or []
    if isinstance(raw_candidates, str):
        raw_candidates = [raw_candidates]
    if isinstance(raw_candidates, list):
        for candidate in raw_candidates:
            selector = str(candidate or "").strip()
            if selector and selector not in candidates:
                candidates.append(selector)

    for key in (
        "interactiveSelector",
        "interactive_selector",
        "element",
        "selector",
        "targetSelector",
        "target_selector",
    ):
        selector = str(event.get(key) or "").strip()
        if selector and selector not in candidates:
            candidates.append(selector)

    return candidates[0] if candidates else ""


def _log_event_summary(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("value")
    return {
        "action": _event_action(event),
        "selector": _event_selector(event),
        "input_type": event.get("inputType") or event.get("input_type") or "",
        "value_len": len(str(value)) if value not in (None, "") else 0,
        "has_id": bool(event.get("id")),
    }


def _log_action_summary(action: CrawlAction) -> dict[str, Any]:
    return {
        "type": action.action_type,
        "selector": action.selector,
        "input_type": (action.metadata or {}).get("type") or "",
        "value_len": len(str(action.value)) if action.value not in (None, "") else 0,
    }


def _compact_manual_events(
    events: list[dict[str, Any]],
    *,
    display_safe: bool,
) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for event in events:
        next_event = dict(event)
        action = _event_action(next_event)
        selector = _event_selector(next_event)

        if _event_is_input_like(next_event):
            if (
                compacted
                and _event_action(compacted[-1]) == "click"
                and _event_selector(compacted[-1]) == selector
            ):
                compacted.pop()

            if (
                compacted
                and _event_is_input_like(compacted[-1])
                and _event_selector(compacted[-1]) == selector
            ):
                compacted[-1] = next_event
                continue

        if action or selector:
            compacted.append(next_event)

    return compacted


def _pending_input_group_selector(events: list[dict[str, Any]]) -> str:
    compacted = _compact_manual_events(events, display_safe=False)
    if len(compacted) != 1:
        return ""

    event = compacted[0]
    if not _event_is_input_like(event):
        return ""
    return _event_selector(event)


def _action_value_is_docgen_safe(value: Any) -> bool:
    if isinstance(value, str):
        if not value.strip():
            return False
        try:
            actions = json.loads(value)
        except Exception:
            return False
    else:
        actions = value

    if not isinstance(actions, list) or not actions:
        return False

    return all(
        isinstance(action, dict) and bool(str(action.get("s") or "").strip())
        for action in actions
    )


def _transition_is_docgen_safe(transition: AbstractTransition) -> bool:
    return bool(str(transition.locator_value or "").strip()) and _action_value_is_docgen_safe(
        transition.action_value
    )


def _action_selector_candidates(action: CrawlAction) -> list[str]:
    candidates: list[str] = []

    metadata = action.metadata or {}
    raw_candidates = metadata.get("selector_candidates") or []
    if isinstance(raw_candidates, str):
        raw_candidates = [raw_candidates]
    if isinstance(raw_candidates, list):
        for candidate in raw_candidates:
            selector = str(candidate or "").strip()
            if selector and selector not in candidates:
                candidates.append(selector)

    selector = str(action.selector or "").strip()
    if selector and selector not in candidates:
        candidates.append(selector)

    return candidates


def _copy_action_with_selector(action: CrawlAction, selector: str) -> CrawlAction:
    if action.selector == selector:
        return action

    metadata = dict(action.metadata or {})
    metadata["original_selector"] = action.selector
    metadata["resolved_selector"] = selector
    description = str(action.description or action.action_type)
    if action.selector and action.selector in description:
        description = description.replace(action.selector, selector)
    elif selector:
        description = f"{description} [{selector}]"

    return CrawlAction(
        action_id=action.action_id,
        action_type=action.action_type,
        selector=selector,
        value=action.value,
        description=description,
        metadata=metadata,
    )


@dataclass
class ManualStateSnapshot:
    state: AbstractState
    storage_state: Any | None


@dataclass
class ManualTransitionSnapshot:
    step_id: str
    source_index: int
    target_index: int
    transition: AbstractTransition
    actions: list[CrawlAction]
    events: list[dict[str, Any]]
    created_at: str


class ManualSegmentRecorder:
    def __init__(
        self,
        *,
        db: Any,
        redis: Any,
        graph_builder: Any,
        graph_id: str,
        session_id: str,
        page: Any,
        job: CrawlJob,
        selector_resolver: SelectorResolver | None = None,
    ) -> None:
        self._db = db
        self._redis = redis
        self._graph_builder = graph_builder
        self._graph_id = graph_id
        self._session_id = session_id
        self._page = page
        self._job = job
        self._selector_resolver = selector_resolver
        self._lock = asyncio.Lock()
        self._active = False
        self._rewinding = False
        self._flow_revision = 0
        self._states: list[ManualStateSnapshot] = []
        self._transitions: list[ManualTransitionSnapshot] = []
        self._current_state_idx: int | None = None
        self._checkpoint_candidate_idx = 0
        self._segment_start_state_idx: int | None = None
        self._segment_start_transition_idx = 0
        self._checkpoint_hash = ""
        self._pending_events: list[dict[str, Any]] = []
        self._pending_updated_at = 0.0
        self._last_browser_input_at = 0.0
        self.state_count = 0
        self.transition_count = 0

    @property
    def active(self) -> bool:
        return self._active

    @property
    def transition_refs(self) -> list[str]:
        return [snapshot.transition.transition_id for _, snapshot in self._active_transition_entries()]

    def set_page(self, page: Any) -> None:
        self._page = page

    def mark_browser_input(self) -> None:
        self._last_browser_input_at = time.monotonic()

    def begin_rewind(self) -> None:
        self._rewinding = True

    def cancel_rewind(self) -> None:
        self._rewinding = False

    def should_flush_pending_events(self) -> bool:
        if not self._pending_events:
            return False
        if (time.monotonic() - self._pending_updated_at) < PENDING_EVENT_FLUSH_SECONDS:
            return False

        flushable_actions = {"input", "change", "hover"}
        return all(
            str(event.get("action") or "") in flushable_actions
            for event in self._pending_events
        )

    def _waiting_for_dom_event(self) -> bool:
        if self._last_browser_input_at <= 0:
            return False
        return (time.monotonic() - self._last_browser_input_at) < PENDING_EVENT_FLUSH_SECONDS

    async def initialize(self) -> None:
        async with self._lock:
            if self._current_state_idx is not None:
                return
            snapshot = await self._capture_snapshot()
            self._states.append(snapshot)
            self._current_state_idx = 0
            self._checkpoint_candidate_idx = 0

    async def start(self) -> dict[str, Any]:
        await self.initialize()
        await self.flush_current_state(force_pending=True)
        async with self._lock:
            if self._active:
                raise RuntimeError("A manual flow is already active")
            if self._current_state_idx is None:
                raise RuntimeError("Manual session is not ready")

            start_state_idx = min(self._checkpoint_candidate_idx, self._current_state_idx)
            self._active = True
            self._flow_revision += 1
            self._segment_start_state_idx = start_state_idx
            self._segment_start_transition_idx = self._first_transition_index_at_or_after(start_state_idx)
            checkpoint = self._states[start_state_idx].state
            self._checkpoint_hash = checkpoint.state_hash
            self._pending_events = []
            self._pending_updated_at = 0.0
            steps = [
                self._step_payload(snapshot, index)
                for index, snapshot in self._active_transition_entries()
            ]
            return {
                "sessionId": self._session_id,
                "pageUrl": checkpoint.url,
                "title": checkpoint.title,
                "checkpointHash": checkpoint.state_hash,
                "flowRevision": self._flow_revision,
                "steps": steps,
                "timestamp": _utc_now(),
            }

    async def record_event(self, event: dict[str, Any]) -> bool:
        async with self._lock:
            self._pending_events.append(event)
            self._pending_updated_at = time.monotonic()
            return self._active

    async def publish_pending_events(self) -> list[dict[str, Any]]:
        return await self.flush_current_state(force_pending=True)

    async def flush_current_state(self, *, force_pending: bool = False) -> list[dict[str, Any]]:
        async with self._lock:
            if self._rewinding:
                return []
            if self._current_state_idx is None:
                return []

            semantic = await self._page.evaluate(STATE_HASH_SCRIPT)
            next_hash = StateManager.hash_content(str(semantic))
            source_index = self._current_state_idx
            source_snapshot = self._states[source_index]
            changed = next_hash != source_snapshot.state.state_hash
            pending_age = time.monotonic() - self._pending_updated_at
            if changed and not self._pending_events and not force_pending and self._waiting_for_dom_event():
                return []
            if (
                changed
                and self._pending_events
                and not force_pending
                and pending_age < PENDING_EVENT_FLUSH_SECONDS
                and _pending_input_group_selector(self._pending_events)
            ):
                return []
            if not changed and not (force_pending and self._pending_events):
                return []

            events = list(self._pending_events)
            self._pending_events = []
            self._pending_updated_at = 0.0

            if changed:
                target_snapshot = await self._capture_snapshot()
                self._states.append(target_snapshot)
                target_index = len(self._states) - 1
                if not self._active and target_snapshot.state.url != source_snapshot.state.url:
                    self._checkpoint_candidate_idx = source_index
            else:
                target_snapshot = source_snapshot
                target_index = source_index

            if changed and not events:
                step = self._merge_implicit_state_change(source_index, target_index)
                self._current_state_idx = target_index
                if step is None:
                    self._advance_empty_active_segment_checkpoint(target_index)
                return [step] if step is not None else []

            step = await self._append_transition(source_index, target_index, events)
            self._current_state_idx = target_index
            if changed and step is None:
                self._advance_empty_active_segment_checkpoint(target_index)
            return [step] if step is not None else []

    async def finish_manual_flow(self) -> dict[str, Any]:
        return await self._finish(TestFlowType.MANUAL)

    async def report_bug(self, details: dict[str, Any]) -> dict[str, Any]:
        completed = await self._finish(TestFlowType.BUG_REPRODUCTION)
        bug_payload = {
            "sessionId": self._session_id,
            "flowId": completed["flowId"],
            "checkpointHash": completed["checkpointHash"],
            "transitionIds": completed["transitionIds"],
            "summary": str(details.get("summary") or "").strip(),
            "severity": str(details.get("severity") or "medium").strip() or "medium",
            "currentUrl": str(getattr(self._page, "url", "") or ""),
            "recordedEvents": completed["recordedEvents"] if details.get("includeSteps", True) else [],
        }
        report_response = await _create_manual_bug_report(bug_payload)
        return {
            **completed,
            "summary": bug_payload["summary"],
            "severity": bug_payload["severity"],
            "reportId": report_response.get("report", {}).get("id"),
            "jobId": report_response.get("jobId"),
        }

    async def _finish(self, flow_type: TestFlowType) -> dict[str, Any]:
        await asyncio.sleep(0.1)
        await self.flush_current_state(force_pending=True)
        async with self._lock:
            if not self._active:
                raise RuntimeError("No manual flow is active")
            active_transitions = [snapshot for _, snapshot in self._active_transition_entries()]
            if not active_transitions:
                raise RuntimeError("No transitions were recorded for this flow")

            projectable_transitions = await self._projectable_active_segment(active_transitions)
            if not projectable_transitions:
                raise RuntimeError("No labelable transitions were recorded for this flow")

            transition_refs = await self._persist_active_segment(projectable_transitions)
            verified = await self._verify_active_segment(transition_refs)
            if not verified:
                raise RuntimeError("Manual flow graph did not resolve in Neo4j")

            recorded_events = self._active_recorded_events()
            self._active = False
            self._checkpoint_candidate_idx = self._current_state_idx or self._checkpoint_candidate_idx
            self._segment_start_state_idx = None
            self._segment_start_transition_idx = len(self._transitions)

        async with self._db() as s:
            flow_id = await create_test_flow(
                s,
                self._session_id,
                self._checkpoint_hash,
                transition_refs,
                flow_type,
            )

        return {
            "sessionId": self._session_id,
            "flowId": flow_id,
            "checkpointHash": self._checkpoint_hash,
            "transitionIds": list(transition_refs),
            "testFlowType": flow_type.value,
            "stepCount": len(transition_refs),
            "recordedEvents": recorded_events,
            "timestamp": _utc_now(),
        }

    async def prepare_rewind(self, step_id: str | None) -> dict[str, Any]:
        await self.flush_current_state(force_pending=True)
        async with self._lock:
            if not self._active or self._segment_start_state_idx is None:
                raise RuntimeError("No manual flow is active")

            active_entries = self._active_transition_entries()
            if step_id:
                keep_relative_index = next(
                    (
                        relative_index
                        for relative_index, (_, snapshot) in enumerate(active_entries)
                        if snapshot.step_id == step_id
                    ),
                    None,
                )
                if keep_relative_index is None:
                    raise RuntimeError("Selected step is not part of the active flow")
                keep_count = keep_relative_index + 1
            else:
                keep_count = 0

            kept_entries = active_entries[:keep_count]
            target_state_idx = (
                kept_entries[-1][1].target_index
                if kept_entries
                else self._segment_start_state_idx
            )
            checkpoint = self._states[self._segment_start_state_idx]
            target = self._states[target_state_idx].state
            actions = [
                action
                for _, snapshot in kept_entries
                for action in snapshot.actions
            ]
            removed_step_ids = [snapshot.step_id for _, snapshot in active_entries[keep_count:]]
            kept_step_ids = [snapshot.step_id for _, snapshot in kept_entries]

            return {
                "checkpointUrl": checkpoint.state.url,
                "checkpointHash": checkpoint.state.state_hash,
                "storageState": checkpoint.storage_state,
                "actions": actions,
                "expectedStateHash": target.state_hash,
                "targetStateIndex": target_state_idx,
                "keepTransitionCount": keep_count,
                "keptStepIds": kept_step_ids,
                "removedStepIds": removed_step_ids,
            }

    async def commit_rewind(self, plan: dict[str, Any], page: Any) -> dict[str, Any]:
        async with self._lock:
            if not self._active or self._segment_start_state_idx is None:
                raise RuntimeError("No manual flow is active")

            keep_count = int(plan["keepTransitionCount"])
            target_state_idx = int(plan["targetStateIndex"])
            cut_transition_idx = self._segment_start_transition_idx + keep_count
            self._transitions = self._transitions[:cut_transition_idx]
            self._states = self._states[: target_state_idx + 1]
            self._current_state_idx = target_state_idx
            self._pending_events = []
            self._pending_updated_at = 0.0
            self._page = page
            self._flow_revision += 1
            self._rewinding = False
            target = self._states[target_state_idx].state
            steps = [
                self._step_payload(snapshot, index)
                for index, snapshot in self._active_transition_entries()
            ]
            return {
                "sessionId": self._session_id,
                "checkpointHash": self._checkpoint_hash,
                "stateHash": target.state_hash,
                "pageUrl": target.url,
                "title": target.title,
                "flowRevision": self._flow_revision,
                "steps": steps,
                "keptStepIds": plan["keptStepIds"],
                "removedStepIds": plan["removedStepIds"],
                "timestamp": _utc_now(),
            }

    def _merge_implicit_state_change(
        self,
        source_index: int,
        target_index: int,
    ) -> dict[str, Any] | None:
        if not self._transitions:
            return None

        transition_index = len(self._transitions) - 1
        snapshot = self._transitions[transition_index]
        if snapshot.target_index != source_index:
            return None
        if not snapshot.actions or not all(_action_has_selector(action) for action in snapshot.actions):
            return None

        source = self._states[snapshot.source_index].state
        target = self._states[target_index].state
        snapshot.target_index = target_index
        snapshot.transition = _build_manual_transition(
            graph_id=self._graph_id,
            session_id=self._session_id,
            source=source,
            target=target,
            actions=snapshot.actions,
            unique_key=snapshot.step_id,
        )

        if self._active and transition_index >= self._segment_start_transition_idx:
            return self._step_payload(snapshot, transition_index)
        return None

    def _advance_empty_active_segment_checkpoint(self, target_index: int) -> None:
        if not self._active:
            return
        if self._active_transition_entries():
            return

        target = self._states[target_index].state
        self._segment_start_state_idx = target_index
        self._segment_start_transition_idx = len(self._transitions)
        self._checkpoint_hash = target.state_hash

    async def _append_transition(
        self,
        source_index: int,
        target_index: int,
        events: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        source = self._states[source_index].state
        target = self._states[target_index].state
        action_events = _compact_manual_events(events, display_safe=False)
        display_events = _compact_manual_events(events, display_safe=False)
        actions = [
            action
            for action in map_steps_to_actions(action_events, fallback_url=target.url or source.url)
            if _action_has_selector(action)
        ]
        logger.info(
            "Manual recorder mapping events session=%s source=%s target=%s raw=%s action_events=%s display_events=%s mapped_actions=%s",
            self._session_id,
            source.state_hash,
            target.state_hash,
            [_log_event_summary(event) for event in events],
            [_log_event_summary(event) for event in action_events],
            [_log_event_summary(event) for event in display_events],
            [_log_action_summary(action) for action in actions],
        )
        actions = await self._resolve_action_selectors(source.html, actions)
        if not actions:
            logger.info(
                "Manual recorder skipped transition after selector resolution session=%s source=%s target=%s",
                self._session_id,
                source.state_hash,
                target.state_hash,
            )
            return None

        coalesced = self._coalesce_input_transition(
            source_index,
            target_index,
            actions,
            display_events,
        )
        if coalesced is not None:
            return coalesced

        step_id = str(uuid4())
        transition = _build_manual_transition(
            graph_id=self._graph_id,
            session_id=self._session_id,
            source=source,
            target=target,
            actions=actions,
            unique_key=step_id,
        )
        transition_index = len(self._transitions)
        snapshot = ManualTransitionSnapshot(
            step_id=step_id,
            source_index=source_index,
            target_index=target_index,
            transition=transition,
            actions=actions,
            events=display_events,
            created_at=_utc_now(),
        )
        self._transitions.append(snapshot)
        if self._active and transition_index >= self._segment_start_transition_idx:
            logger.info(
                "Manual recorder appended step session=%s step=%s index=%s actions=%s display_events=%s",
                self._session_id,
                step_id,
                transition_index,
                [_log_action_summary(action) for action in actions],
                [_log_event_summary(event) for event in display_events],
            )
            return self._step_payload(snapshot, transition_index)
        return None

    def _coalesce_input_transition(
        self,
        source_index: int,
        target_index: int,
        actions: list[CrawlAction],
        display_events: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        selector = _input_action_selector(actions)
        if not selector or not self._active or not self._transitions:
            return None

        transition_index = len(self._transitions) - 1
        if transition_index < self._segment_start_transition_idx:
            return None

        snapshot = self._transitions[transition_index]
        if snapshot.target_index != source_index:
            return None

        previous_input_selector = _input_action_selector(snapshot.actions)
        previous_click_selector = _focus_click_selector(snapshot.actions)
        replacing_focus_click = (
            previous_click_selector == selector
            and snapshot.source_index == snapshot.target_index
        )
        if previous_input_selector != selector and not replacing_focus_click:
            return None

        source = self._states[snapshot.source_index].state
        target = self._states[target_index].state
        snapshot.target_index = target_index
        snapshot.actions = actions
        snapshot.events = (
            display_events
            if replacing_focus_click
            else _compact_manual_events([*snapshot.events, *display_events], display_safe=False)
        )
        snapshot.transition = _build_manual_transition(
            graph_id=self._graph_id,
            session_id=self._session_id,
            source=source,
            target=target,
            actions=actions,
            unique_key=snapshot.step_id,
        )
        logger.info(
            "Manual recorder coalesced step session=%s step=%s index=%s replacing_focus_click=%s actions=%s display_events=%s",
            self._session_id,
            snapshot.step_id,
            transition_index,
            replacing_focus_click,
            [_log_action_summary(action) for action in actions],
            [_log_event_summary(event) for event in snapshot.events],
        )
        return self._step_payload(snapshot, transition_index)

    async def _resolve_action_selectors(
        self,
        source_html: str,
        actions: list[CrawlAction],
    ) -> list[CrawlAction]:
        resolved_actions: list[CrawlAction] = []
        for action in actions:
            resolved = await self._resolve_action_selector(source_html, action)
            if resolved is not None:
                resolved_actions.append(resolved)
        return resolved_actions

    async def _resolve_action_selector(
        self,
        source_html: str,
        action: CrawlAction,
    ) -> CrawlAction | None:
        for selector in _action_selector_candidates(action):
            if await self._selector_matches_html(source_html, selector):
                return _copy_action_with_selector(action, selector)
        return None

    async def _selector_matches_html(self, html: str, selector: str) -> bool:
        selector = str(selector or "").strip()
        if not selector or not str(html or "").strip():
            return False

        if self._selector_resolver is not None:
            return bool(await self._selector_resolver(html, selector))

        context = getattr(self._page, "context", None)
        if context is None:
            return False

        temp_page = await context.new_page()
        try:
            await temp_page.set_content(html)
            return await temp_page.locator(selector).first.count() > 0
        except Exception:
            return False
        finally:
            try:
                await temp_page.close()
            except Exception:
                pass

    async def _projectable_active_segment(
        self,
        active_transitions: list[ManualTransitionSnapshot],
    ) -> list[ManualTransitionSnapshot]:
        projectable: list[ManualTransitionSnapshot] = []
        for snapshot in active_transitions:
            source = self._states[snapshot.source_index].state
            target = self._states[snapshot.target_index].state
            snapshot.transition = _build_manual_transition(
                graph_id=self._graph_id,
                session_id=self._session_id,
                source=source,
                target=target,
                actions=snapshot.actions,
                unique_key=snapshot.step_id,
            )
            if not _transition_is_docgen_safe(snapshot.transition):
                logger.warning(
                    "Skipping manual transition %s because it is not docgen-safe",
                    snapshot.step_id,
                )
                continue
            if not await self._selector_matches_html(source.html, snapshot.transition.locator_value):
                logger.warning(
                    "Skipping manual transition %s because selector did not resolve: %s",
                    snapshot.step_id,
                    snapshot.transition.locator_value,
                )
                continue
            projectable.append(snapshot)
        return projectable

    async def _capture_snapshot(self) -> ManualStateSnapshot:
        state = await _capture_manual_state(self._page, self._job)
        return ManualStateSnapshot(
            state=state,
            storage_state=await self._page.context.storage_state(),
        )

    async def _persist_state_snapshot(self, snapshot: ManualStateSnapshot) -> None:
        created = await self._graph_builder.add_state(
            self._graph_id,
            snapshot.state,
            enqueue=False,
            session_id=self._session_id,
        )
        if created:
            self.state_count += 1
        await self._graph_builder.set_state_properties(
            self._graph_id,
            snapshot.state.state_hash,
            {
                "checkpoint_url": snapshot.state.url,
                "checkpoint_state_hash": snapshot.state.state_hash,
                "checkpoint_storage_state_json": snapshot.storage_state,
            },
        )

    async def _persist_active_segment(self, active_transitions: list[ManualTransitionSnapshot]) -> list[str]:
        state_indices = self._active_state_indices(active_transitions)
        for index in state_indices:
            await self._persist_state_snapshot(self._states[index])

        transition_refs: list[str] = []
        for snapshot in active_transitions:
            created = await self._graph_builder.add_transition(snapshot.transition)
            if created:
                self.transition_count += 1
            transition_refs.append(snapshot.transition.transition_id)
        return transition_refs

    async def _verify_active_segment(self, transition_refs: list[str]) -> bool:
        verifier = getattr(self._graph_builder, "verify_bdd_flow", None)
        if verifier is None:
            return True
        return bool(
            await verifier(
                self._graph_id,
                self._session_id,
                self._checkpoint_hash,
                transition_refs,
            )
        )

    def _active_transition_entries(self) -> list[tuple[int, ManualTransitionSnapshot]]:
        if not self._active:
            return []
        return list(enumerate(self._transitions))[self._segment_start_transition_idx :]

    def _active_state_indices(self, active_transitions: list[ManualTransitionSnapshot]) -> list[int]:
        indices: list[int] = []
        if self._segment_start_state_idx is not None:
            indices.append(self._segment_start_state_idx)
        for snapshot in active_transitions:
            indices.extend([snapshot.source_index, snapshot.target_index])

        seen: set[int] = set()
        ordered: list[int] = []
        for index in indices:
            if index not in seen:
                seen.add(index)
                ordered.append(index)
        return ordered

    def _active_recorded_events(self) -> list[dict[str, Any]]:
        return [
            event
            for _, snapshot in self._active_transition_entries()
            for event in snapshot.events
        ]

    def _first_transition_index_at_or_after(self, state_idx: int) -> int:
        for index, snapshot in enumerate(self._transitions):
            if snapshot.source_index >= state_idx:
                return index
        return len(self._transitions)

    def _step_payload(self, snapshot: ManualTransitionSnapshot, transition_index: int) -> dict[str, Any]:
        source = self._states[snapshot.source_index].state
        target = self._states[snapshot.target_index].state
        display_actions = [_display_action(action) for action in snapshot.actions]
        primary = display_actions[-1]
        description = (
            sequence_description(display_actions)
            if any(_action_is_password(action) for action in snapshot.actions)
            else snapshot.transition.action_description
        )
        return {
            "id": snapshot.step_id,
            "stepId": snapshot.step_id,
            "index": transition_index - self._segment_start_transition_idx + 1,
            "flowRevision": self._flow_revision,
            "transitionId": snapshot.transition.transition_id,
            "sourceStateHash": source.state_hash,
            "targetStateHash": target.state_hash,
            "sourceUrl": source.url,
            "targetUrl": target.url,
            "pageUrl": target.url,
            "title": target.title,
            "timestamp": snapshot.created_at,
            "description": description,
            "action": primary.action_type,
            "selector": primary.selector,
            "value": primary.value,
            "events": snapshot.events,
            "actions": [
                {
                    "id": action.action_id,
                    "type": action.action_type,
                    "selector": action.selector,
                    "value": action.value,
                    "description": action.description,
                    "metadata": action.metadata,
                }
                for action in display_actions
            ],
        }


async def _install_dom_recorder(
    context: Any,
    session_id: str,
    event_queue: asyncio.Queue[dict[str, Any]],
    pages: list[Any] | None = None,
) -> None:
    async def record_flow_event(source: Any, payload: Any) -> None:
        if not isinstance(payload, dict):
            return

        source_page = _source_value(source, "page")
        source_frame = _source_value(source, "frame")
        event = {
            "id": str(uuid4()),
            "sessionId": session_id,
            "timestamp": _utc_now(),
            "pageUrl": str(getattr(source_page, "url", "") or ""),
            "frameUrl": str(getattr(source_frame, "url", "") or ""),
            **payload,
        }
        await event_queue.put(event)

    await context.expose_binding("__recordFlowEvent", record_flow_event)
    await context.add_init_script(DOM_RECORDER_SCRIPT)
    for page in pages or []:
        try:
            await page.evaluate(DOM_RECORDER_SCRIPT)
        except Exception:
            logger.debug("Failed to install manual recorder script on active page", exc_info=True)


async def _send_ws(ws: aiohttp.ClientWebSocketResponse, send_lock: asyncio.Lock, payload: dict[str, Any]) -> None:
    if ws.closed:
        return
    async with send_lock:
        if not ws.closed:
            await ws.send_json(payload)


class ManualSessionIdleTTL:
    def __init__(
        self,
        *,
        ttl_seconds: int,
        ws: aiohttp.ClientWebSocketResponse,
        send_lock: asyncio.Lock,
        timeout_event: asyncio.Event,
    ) -> None:
        self._ttl_seconds = max(1, int(ttl_seconds))
        self._ws = ws
        self._send_lock = send_lock
        self._timeout_event = timeout_event
        self._lock = asyncio.Lock()
        self._last_activity_at = time.monotonic()
        self._last_emit_at = 0.0
        self._reset_at = datetime.now(UTC)

    async def reset(self, *, force_emit: bool = False) -> None:
        payload: dict[str, Any] | None = None
        async with self._lock:
            now = time.monotonic()
            self._last_activity_at = now
            self._reset_at = datetime.now(UTC)
            if force_emit or (now - self._last_emit_at) >= 1:
                self._last_emit_at = now
                payload = self._payload_locked(remaining_seconds=self._ttl_seconds)

        if payload is not None:
            await _send_ws(self._ws, self._send_lock, payload)

    async def monitor(self) -> None:
        interval = min(TTL_MONITOR_MAX_INTERVAL_SECONDS, max(1.0, self._ttl_seconds / 10))
        while True:
            await asyncio.sleep(interval)
            async with self._lock:
                elapsed = time.monotonic() - self._last_activity_at
                remaining = max(0, int(self._ttl_seconds - elapsed))
                expired = elapsed >= self._ttl_seconds
                payload = self._payload_locked(remaining_seconds=remaining)

            await _send_ws(self._ws, self._send_lock, payload)
            if expired:
                self._timeout_event.set()
                await _send_ws(
                    self._ws,
                    self._send_lock,
                    {
                        "type": "session.closed",
                        "status": "aborted",
                        "reason": "idle_timeout",
                    },
                )
                await self._ws.close()
                return

    def _payload_locked(self, *, remaining_seconds: int) -> dict[str, Any]:
        expires_at = self._reset_at + timedelta(seconds=self._ttl_seconds)
        return {
            "type": "session.ttl",
            "ttlSeconds": self._ttl_seconds,
            "remainingSeconds": max(0, int(remaining_seconds)),
            "expiresAt": expires_at.isoformat().replace("+00:00", "Z"),
            "resetAt": self._reset_at.isoformat().replace("+00:00", "Z"),
        }


async def _event_sender(
    ws: aiohttp.ClientWebSocketResponse,
    send_lock: asyncio.Lock,
    event_queue: asyncio.Queue[dict[str, Any]],
    recorder: ManualSegmentRecorder | None = None,
    activity_reset: Callable[[], Awaitable[None]] | None = None,
    step_queue: asyncio.Queue[dict[str, Any]] | None = None,
) -> None:
    while True:
        event = await event_queue.get()
        should_emit = True
        if recorder is not None:
            should_emit = await recorder.record_event(event)
        logger.info(
            "Manual recorder received event session=%s emit=%s event=%s",
            event.get("sessionId") or "",
            should_emit,
            _log_event_summary(event),
        )
        if activity_reset is not None:
            await activity_reset()
        if should_emit:
            await _send_ws(ws, send_lock, {"type": "recorded.event", "event": event})


async def _step_sender(
    ws: aiohttp.ClientWebSocketResponse,
    send_lock: asyncio.Lock,
    step_queue: asyncio.Queue[dict[str, Any]],
    activity_reset: Callable[[], Awaitable[None]] | None = None,
) -> None:
    while True:
        step = await step_queue.get()
        logger.info(
            "Manual recorder sending step session=%s step=%s action=%s selector=%s value_len=%s events=%s",
            step.get("sessionId") or "",
            step.get("id") or step.get("stepId") or "",
            step.get("action") or "",
            step.get("selector") or "",
            len(str(step.get("value") or "")),
            [_log_event_summary(event) for event in step.get("events") or [] if isinstance(event, dict)],
        )
        if activity_reset is not None:
            await activity_reset()
        await _send_ws(
            ws,
            send_lock,
            {
                "type": "recorded.step",
                "flowRevision": step.get("flowRevision"),
                "step": step,
            },
        )


def _drain_queue(queue: asyncio.Queue[Any]) -> None:
    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            return


async def _start_screencast(
    page: Any,
    ws: aiohttp.ClientWebSocketResponse,
    send_lock: asyncio.Lock,
) -> tuple[Any, set[asyncio.Task[None]]]:
    cdp = await page.context.new_cdp_session(page)
    pending: set[asyncio.Task[None]] = set()

    await cdp.send("Page.enable")

    async def handle_frame(frame: dict[str, Any]) -> None:
        try:
            data = frame.get("data")
            if data:
                await _send_ws(
                    ws,
                    send_lock,
                    {
                        "type": "browser.frame",
                        "dataUrl": f"data:image/jpeg;base64,{data}",
                        "metadata": frame.get("metadata") or {},
                        "viewport": {
                            "width": VIEWPORT_WIDTH,
                            "height": VIEWPORT_HEIGHT,
                        },
                    },
                )
        finally:
            session_id = frame.get("sessionId")
            if session_id is not None:
                try:
                    await cdp.send("Page.screencastFrameAck", {"sessionId": session_id})
                except Exception:
                    pass

    def on_frame(frame: dict[str, Any]) -> None:
        task = asyncio.create_task(handle_frame(frame))
        pending.add(task)
        task.add_done_callback(pending.discard)

    cdp.on("Page.screencastFrame", on_frame)
    await cdp.send(
        "Page.startScreencast",
        {
            "format": "jpeg",
            "quality": 70,
            "maxWidth": VIEWPORT_WIDTH,
            "maxHeight": VIEWPORT_HEIGHT,
            "everyNthFrame": 1,
        },
    )
    return cdp, pending


async def _stop_screencast(cdp: Any | None, pending: set[asyncio.Task[None]]) -> None:
    if cdp is not None:
        try:
            await cdp.send("Page.stopScreencast")
        except Exception:
            pass

    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def _normalize_button(value: Any) -> str:
    if value == 1:
        return "middle"
    if value == 2:
        return "right"
    if value in {"left", "middle", "right"}:
        return str(value)
    return "left"


async def _inspect_element_at(page: Any, x: int, y: int) -> dict[str, Any] | None:
    state_hash = ""
    try:
        semantic = await page.evaluate(STATE_HASH_SCRIPT)
        state_hash = StateManager.hash_content(str(semantic))
    except Exception:
        state_hash = ""

    try:
        element = await page.evaluate(
            INSPECT_ELEMENT_SCRIPT,
            {"x": x, "y": y, "stateHash": state_hash},
        )
    except Exception:
        logger.debug("Failed to inspect explicit hover target", exc_info=True)
        return None

    return element if isinstance(element, dict) else None


def _synthetic_hover_event(
    session_id: str,
    element: dict[str, Any],
    x: int,
    y: int,
) -> dict[str, Any]:
    selector = str(element.get("selector") or "")
    raw_candidates = element.get("selectorCandidates") or []
    selector_candidates = raw_candidates if isinstance(raw_candidates, list) else []
    tag = str(element.get("tag") or "")
    text = str(element.get("text") or "")
    accessible_name = str(element.get("accessibleName") or "")
    label = accessible_name or text or selector or tag or "element"
    box = element.get("box") if isinstance(element.get("box"), dict) else None
    viewport = (
        element.get("viewport")
        if isinstance(element.get("viewport"), dict)
        else {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}
    )

    return {
        "id": str(uuid4()),
        "sessionId": session_id,
        "timestamp": _utc_now(),
        "action": "hover",
        "pageUrl": str(element.get("pageUrl") or ""),
        "frameUrl": "",
        "selector": selector,
        "selectorCandidates": selector_candidates,
        "interactiveSelector": selector,
        "element": selector,
        "targetSelector": selector,
        "x": x,
        "y": y,
        "pageX": x,
        "pageY": y,
        "button": 2,
        "tag": tag or None,
        "targetTag": tag or None,
        "label": label,
        "text": text,
        "accessibleName": accessible_name,
        "targetText": text,
        "targetAccessibleName": accessible_name,
        "href": None,
        "elementBox": box,
        "targetElementBox": box,
        "viewport": viewport,
    }


async def _handle_hover_input(
    page: Any,
    session_id: str,
    x: int,
    y: int,
) -> dict[str, Any] | None:
    element = await _inspect_element_at(page, x, y)
    await page.mouse.move(x, y)
    if element is None:
        return None
    return _synthetic_hover_event(session_id, element, x, y)


async def _handle_mouse_input(
    page: Any,
    input_payload: dict[str, Any],
    session_id: str,
) -> dict[str, Any] | None:
    action = str(input_payload.get("action") or "")
    x = round(float(input_payload.get("x") or 0))
    y = round(float(input_payload.get("y") or 0))
    button = _normalize_button(input_payload.get("button"))

    if action == "move":
        return None
    if action == "hover":
        return await _handle_hover_input(page, session_id, x, y)
    elif action == "down":
        await page.mouse.move(x, y)
        await page.mouse.down(button=button)
    elif action == "up":
        await page.mouse.move(x, y)
        await page.mouse.up(button=button)
    elif action == "wheel":
        await page.mouse.wheel(
            float(input_payload.get("deltaX") or 0),
            float(input_payload.get("deltaY") or 0),
        )
    return None


async def _handle_keyboard_input(page: Any, input_payload: dict[str, Any]) -> None:
    key = str(input_payload.get("key") or "")
    if not key:
        return

    modifiers = [
        ("Control", bool(input_payload.get("ctrlKey"))),
        ("Meta", bool(input_payload.get("metaKey"))),
        ("Alt", bool(input_payload.get("altKey"))),
        ("Shift", bool(input_payload.get("shiftKey")) and len(key) != 1),
    ]
    active_modifiers = [name for name, enabled in modifiers if enabled]

    for modifier in active_modifiers:
        await page.keyboard.down(modifier)

    try:
        if len(key) == 1 and not any(input_payload.get(name) for name in ("ctrlKey", "metaKey", "altKey")):
            await page.keyboard.insert_text(key)
        else:
            await page.keyboard.press(key)
    finally:
        for modifier in reversed(active_modifiers):
            await page.keyboard.up(modifier)


async def _handle_navigation_input(page: Any, input_payload: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    action = str(input_payload.get("action") or "")
    if action != "back":
        return None

    before_url = str(getattr(page, "url", "") or "")
    await page.go_back(wait_until="domcontentloaded", timeout=10000)
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    return {
        "id": str(uuid4()),
        "sessionId": session_id,
        "timestamp": _utc_now(),
        "action": "navigate_back",
        "pageUrl": str(getattr(page, "url", "") or ""),
        "fromUrl": before_url,
        "selector": "",
        "element": "",
        "label": "Browser Back",
    }


async def _handle_browser_input(page: Any, message: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    input_payload = message.get("input")
    if not isinstance(input_payload, dict):
        input_payload = message

    kind = str(input_payload.get("kind") or input_payload.get("type") or "")
    if kind == "mouse":
        return await _handle_mouse_input(page, input_payload, session_id)
    elif kind == "keyboard":
        await _handle_keyboard_input(page, input_payload)
    elif kind == "navigation":
        return await _handle_navigation_input(page, input_payload, session_id)
    return None


async def _execute_replay_action(page: Any, action: CrawlAction, job: CrawlJob) -> None:
    action_type = str(action.action_type or "")
    selector = str(action.selector or "")
    value = str(action.value or "")

    if action_type == "click":
        if not selector:
            raise RuntimeError("Cannot replay click without a selector")
        await page.click(selector, timeout=job.timeout_ms)
    elif action_type == "type":
        if selector:
            await page.fill(selector, value, timeout=job.timeout_ms)
        else:
            await page.keyboard.insert_text(value)
    elif action_type == "select":
        if not selector:
            raise RuntimeError("Cannot replay select without a selector")
        await page.select_option(selector, value, timeout=job.timeout_ms)
    elif action_type == "press":
        if selector:
            await page.press(selector, value, timeout=job.timeout_ms)
        else:
            await page.keyboard.press(value)
    elif action_type == "hover":
        if not selector:
            raise RuntimeError("Cannot replay hover without a selector")
        await page.hover(selector, timeout=job.timeout_ms)
    elif action_type == "navigate":
        if value:
            await page.goto(value, wait_until="domcontentloaded", timeout=job.timeout_ms)
    else:
        raise RuntimeError(f"Cannot replay unsupported action type: {action_type}")

    await _wait_for_page_settle(page, job)


async def _replay_manual_path(
    browser: Any,
    job: CrawlJob,
    session_id: str,
    event_queue: asyncio.Queue[dict[str, Any]],
    plan: dict[str, Any],
) -> tuple[Any, Any]:
    context_kwargs: dict[str, Any] = {
        "viewport": {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        "device_scale_factor": 1,
        "ignore_https_errors": True,
    }
    if plan.get("storageState") is not None:
        context_kwargs["storage_state"] = plan["storageState"]

    new_context = await browser.new_context(**context_kwargs)
    try:
        new_page = await new_context.new_page()
        new_page.set_default_timeout(job.timeout_ms)
        checkpoint_url = str(plan.get("checkpointUrl") or job.base_url)
        await new_page.goto(checkpoint_url, wait_until="domcontentloaded", timeout=job.timeout_ms)
        await _wait_for_page_settle(new_page, job)

        for action in plan.get("actions") or []:
            await _execute_replay_action(new_page, action, job)

        state_hash = StateManager.hash_content(str(await new_page.evaluate(STATE_HASH_SCRIPT)))
        if state_hash != plan.get("expectedStateHash"):
            raise RuntimeError("Replay did not reach the selected step")

        await _install_dom_recorder(new_context, session_id, event_queue, pages=[new_page])
        return new_context, new_page
    except Exception:
        try:
            await new_context.close()
        except Exception:
            pass
        raise


async def _send_navigation(
    ws: aiohttp.ClientWebSocketResponse,
    send_lock: asyncio.Lock,
    page: Any,
    activity_reset: Callable[[], Awaitable[None]] | None = None,
) -> None:
    if activity_reset is not None:
        await activity_reset()
    await _send_ws(
        ws,
        send_lock,
        {
            "type": "browser.navigation",
            "url": page.url,
            "title": await page.title(),
            "timestamp": _utc_now(),
        },
    )


async def _state_monitor(
    recorder: ManualSegmentRecorder,
    step_queue: asyncio.Queue[dict[str, Any]],
) -> None:
    while True:
        await asyncio.sleep(STATE_MONITOR_INTERVAL_SECONDS)
        try:
            steps = await recorder.flush_current_state(
                force_pending=recorder.should_flush_pending_events()
            )
            for step in steps:
                await step_queue.put(step)
        except Exception:
            logger.debug("Manual state monitor flush failed", exc_info=True)


async def manual_record_session(ctx: dict, session_id: str) -> dict[str, Any]:
    db = ctx["db"]

    async with db() as s:
        started = await ensure_started_or_skip_aborted(s, session_id)
        if not started:
            return {"status": "aborted", "session_id": session_id}

    playwright = None
    browser = None
    context = None
    ws: aiohttp.ClientWebSocketResponse | None = None
    cdp = None
    frame_tasks: set[asyncio.Task[None]] = set()
    event_sender_task: asyncio.Task[None] | None = None
    step_sender_task: asyncio.Task[None] | None = None
    state_monitor_task: asyncio.Task[None] | None = None
    ttl_monitor_task: asyncio.Task[None] | None = None
    ttl_timeout_event = asyncio.Event()
    close_outcome = "aborted"
    recorder: ManualSegmentRecorder | None = None

    try:
        async with db() as s:
            (
                config_json,
                base_url,
                _app_version_graph_id,
                _state_count,
                _transition_count,
            ) = await fetch_job_inputs(s, session_id)

        graph_id = session_id
        payload = _build_payload_from_db(config_json, base_url, session_id, graph_id)
        job = CrawlJob.from_dict(payload, config)
        event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        step_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        send_lock = asyncio.Lock()

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=job.headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}",
            ],
        )
        context = await browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            device_scale_factor=1,
            ignore_https_errors=True,
        )
        await _install_dom_recorder(context, session_id, event_queue)

        page = await context.new_page()
        page.set_default_timeout(job.timeout_ms)
        graph_builder = getattr(ctx.get("crawler_worker"), "_graph_builder", None)
        if graph_builder is None:
            raise RuntimeError("crawler graph builder is not available")

        async with aiohttp.ClientSession() as http:
            ws = await http.ws_connect(
                _api_internal_ws_url(session_id),
                headers={"x-coverit-internal-token": _internal_token()},
                heartbeat=20,
            )
            recorder = ManualSegmentRecorder(
                db=db,
                redis=ctx["redis"],
                graph_builder=graph_builder,
                graph_id=graph_id,
                session_id=session_id,
                page=page,
                job=job,
            )
            ttl = ManualSessionIdleTTL(
                ttl_seconds=config.MANUAL_SESSION_IDLE_TTL_SECONDS,
                ws=ws,
                send_lock=send_lock,
                timeout_event=ttl_timeout_event,
            )
            ttl_monitor_task = asyncio.create_task(ttl.monitor())
            event_sender_task = asyncio.create_task(
                _event_sender(ws, send_lock, event_queue, recorder, ttl.reset, step_queue)
            )
            step_sender_task = asyncio.create_task(_step_sender(ws, send_lock, step_queue, ttl.reset))
            state_monitor_task = asyncio.create_task(_state_monitor(recorder, step_queue))

            async def navigation_event() -> None:
                try:
                    await _send_navigation(ws, send_lock, page, ttl.reset)
                except Exception:
                    logger.debug("Failed to send navigation event for %s", session_id, exc_info=True)

            def on_frame_navigated(frame: Any) -> None:
                if frame == page.main_frame:
                    asyncio.create_task(navigation_event())

            async def activate_replayed_page(new_context: Any, new_page: Any) -> None:
                nonlocal context, page, cdp, frame_tasks

                old_context = context
                await _stop_screencast(cdp, frame_tasks)
                context = new_context
                page = new_page
                recorder.set_page(page)
                page.on("framenavigated", on_frame_navigated)
                cdp, frame_tasks = await _start_screencast(page, ws, send_lock)
                await _send_navigation(ws, send_lock, page, ttl.reset)
                if old_context is not None:
                    try:
                        await old_context.close()
                    except Exception:
                        pass

            page.on("framenavigated", on_frame_navigated)

            await ttl.reset()
            await _send_ws(ws, send_lock, {"type": "session.status", "status": "starting_browser"})
            await ttl.reset()
            await page.goto(job.base_url, wait_until="domcontentloaded", timeout=job.timeout_ms)
            try:
                await page.wait_for_load_state(job.page_load_state, timeout=min(job.timeout_ms, 10000))
            except Exception:
                pass

            await recorder.initialize()
            await _send_navigation(ws, send_lock, page, ttl.reset)
            cdp, frame_tasks = await _start_screencast(page, ws, send_lock)
            await ttl.reset()
            await _send_ws(
                ws,
                send_lock,
                {
                    "type": "crawler.ready",
                    "sessionId": session_id,
                    "url": page.url,
                    "title": await page.title(),
                    "viewport": {
                        "width": VIEWPORT_WIDTH,
                        "height": VIEWPORT_HEIGHT,
                    },
                    "timestamp": _utc_now(),
                },
            )
            await ttl.reset()
            await _send_ws(ws, send_lock, {"type": "session.status", "status": "running"})

            async for ws_message in ws:
                if ws_message.type == aiohttp.WSMsgType.TEXT:
                    try:
                        message = json.loads(ws_message.data)
                    except json.JSONDecodeError:
                        await _send_ws(ws, send_lock, {"type": "error", "message": "Invalid JSON"})
                        continue

                    if not isinstance(message, dict):
                        continue

                    message_type = message.get("type")
                    if message_type in {
                        "browser.input",
                        "flow.start",
                        "flow.publish_pending",
                        "flow.finish",
                        "flow.rewind",
                        "bug.report",
                        "session.disconnect",
                    }:
                        await ttl.reset()
                    if message_type == "browser.input":
                        recorder.mark_browser_input()
                        synthetic_event = await _handle_browser_input(page, message, session_id)
                        if synthetic_event is not None:
                            await event_queue.put(synthetic_event)
                    elif message_type == "flow.start":
                        if recorder.active:
                            await _send_ws(ws, send_lock, {"type": "error", "message": "A manual flow is already active"})
                            continue
                        started_payload = await recorder.start()
                        await ttl.reset()
                        await _send_ws(
                            ws,
                            send_lock,
                            {
                                "type": "flow.started",
                                **started_payload,
                            },
                        )
                    elif message_type == "flow.publish_pending":
                        if not recorder.active:
                            await _send_ws(ws, send_lock, {"type": "error", "message": "No manual flow is active"})
                            continue
                        try:
                            published_steps = await recorder.publish_pending_events()
                            for step in published_steps:
                                await step_queue.put(step)
                            await ttl.reset()
                            await _send_ws(
                                ws,
                                send_lock,
                                {
                                    "type": "flow.pending_published",
                                    "sessionId": session_id,
                                    "stepCount": len(published_steps),
                                    "timestamp": _utc_now(),
                                },
                            )
                        except Exception as exc:
                            await _send_ws(ws, send_lock, {"type": "error", "message": str(exc)})
                    elif message_type == "flow.finish":
                        try:
                            completed = await recorder.finish_manual_flow()
                            await ttl.reset()
                            await _send_ws(ws, send_lock, {"type": "flow.completed", **completed})
                        except Exception as exc:
                            await _send_ws(ws, send_lock, {"type": "error", "message": str(exc)})
                    elif message_type == "flow.rewind":
                        rewind_payload = message.get("rewind")
                        if not isinstance(rewind_payload, dict):
                            rewind_payload = message
                        raw_step_id = rewind_payload.get("stepId") or rewind_payload.get("step_id")
                        step_id = str(raw_step_id) if raw_step_id else None
                        try:
                            plan = await recorder.prepare_rewind(step_id)
                            recorder.begin_rewind()
                            _drain_queue(step_queue)
                            new_context, new_page = await _replay_manual_path(
                                browser,
                                job,
                                session_id,
                                event_queue,
                                plan,
                            )
                            await activate_replayed_page(new_context, new_page)
                            rewound = await recorder.commit_rewind(plan, page)
                            _drain_queue(step_queue)
                            await ttl.reset()
                            await _send_ws(ws, send_lock, {"type": "flow.rewound", **rewound})
                        except Exception as exc:
                            recorder.cancel_rewind()
                            await _send_ws(ws, send_lock, {"type": "error", "message": str(exc)})
                    elif message_type == "bug.report":
                        details = message.get("bug")
                        if not isinstance(details, dict):
                            details = message
                        if not str(details.get("summary") or "").strip():
                            await _send_ws(ws, send_lock, {"type": "error", "message": "Bug summary is required"})
                            continue
                        try:
                            reported = await recorder.report_bug(details)
                            await ttl.reset()
                            await _send_ws(ws, send_lock, {"type": "bug.reported", **reported})
                        except Exception as exc:
                            await _send_ws(ws, send_lock, {"type": "error", "message": str(exc)})
                    elif message_type == "session.disconnect":
                        reason = str(message.get("reason") or "")
                        close_outcome = "aborted" if reason == "frontend_disconnected_before_ready" else "completed"
                        break
                elif ws_message.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                    break

            async with db() as s:
                if close_outcome == "completed":
                    await mark_completed_if_running(
                        s,
                        session_id,
                        recorder.state_count if recorder is not None else 0,
                        recorder.transition_count if recorder is not None else 0,
                    )
                else:
                    await mark_aborted_if_active(s, session_id)

            if not ttl_timeout_event.is_set():
                await _send_ws(ws, send_lock, {"type": "session.closed", "status": close_outcome})
            return {"status": close_outcome, "session_id": session_id}

    except asyncio.CancelledError:
        async with db() as s:
            await mark_finished_at_if_aborted(s, session_id)
        raise

    except Exception as exc:
        message = str(exc)
        async with db() as s:
            updated = await mark_failed_if_running(s, session_id, message)
            if not updated:
                await mark_finished_at_if_aborted(s, session_id)
        if ws is not None and not ws.closed:
            try:
                await _send_ws(ws, asyncio.Lock(), {"type": "error", "message": message})
                await _send_ws(ws, asyncio.Lock(), {"type": "session.closed", "status": "failed"})
            except Exception:
                pass
        logger.error("Manual recording session %s failed: %s", session_id, message, exc_info=True)
        raise

    finally:
        if ttl_monitor_task is not None:
            ttl_monitor_task.cancel()
            await asyncio.gather(ttl_monitor_task, return_exceptions=True)

        if state_monitor_task is not None:
            state_monitor_task.cancel()
            await asyncio.gather(state_monitor_task, return_exceptions=True)

        if event_sender_task is not None:
            event_sender_task.cancel()
            await asyncio.gather(event_sender_task, return_exceptions=True)

        if step_sender_task is not None:
            step_sender_task.cancel()
            await asyncio.gather(step_sender_task, return_exceptions=True)

        await _stop_screencast(cdp, frame_tasks)

        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                pass

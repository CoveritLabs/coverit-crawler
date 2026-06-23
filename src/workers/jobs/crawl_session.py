from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.db.repositories.crawl_sessions import (
    fetch_job_inputs,
    fetch_started_at,
    get_session_status,
    mark_completed_if_running,
    mark_failed_if_running,
    mark_finished_at_if_aborted,
)
from src.db.services.crawl_sessions import ensure_started_or_skip_aborted
from src.graph.test_flow_generation.stage2_selecting_best_tf import MAX_TF_TAKEN
from src.models import CrawlJob
from src.utils.coercion import coerce_float, coerce_int
from src.workers.jobs.flows_job import run_find_all_flows

logger = logging.getLogger(__name__)

DEFAULT_TEST_FLOW_GENERATION_CONFIG = {
    "coverage_percentage": 100.0,
    "num_of_tf": 1,
    "num_of_states": 20,
    "min_num_of_states_per_tf": 3,
}

TIMEOUT_SECONDS_BUFFER = 10

def _pick(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source:
            return source.get(key)
    return None


def _timeout_ms(config_json: dict[str, Any], crawler_settings: dict[str, Any]) -> Any:
    explicit = _pick(crawler_settings, "timeout_ms", "timeoutMs")
    if explicit is not None:
        return explicit
    return None


def _timeout_seconds(config_json: dict[str, Any]) -> int | None:
    seconds = coerce_int(_pick(config_json, "timeout_seconds", "timeoutSeconds"), 0)
    return seconds if seconds > 0 else None


def _remaining_timeout_seconds(
    config_json: dict[str, Any],
    started_at: datetime | None,
    *,
    now: datetime | None = None,
) -> float | None:
    timeout_seconds = _timeout_seconds(config_json)
    if timeout_seconds is None:
        return None

    if started_at is None:
        return float(timeout_seconds)

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    started = started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)

    elapsed = max(0.0, (current - started).total_seconds())
    return max(0.0, float(timeout_seconds) - elapsed)


def _slice_seconds(settings: Any, remaining_timeout_seconds: float | None) -> float:
    configured = max(1, int(getattr(settings, "CRAWLER_JOB_SLICE_SECONDS", 600)))
    if remaining_timeout_seconds is None:
        return float(configured)
    return max(0.0, min(float(configured), remaining_timeout_seconds))


def _progress_counts(progress: dict[str, Any]) -> tuple[int, int]:
    return int(progress.get("state_count") or 0), int(progress.get("transition_count") or 0)


def _has_pending_work(progress: dict[str, Any]) -> bool:
    return int(progress.get("pending_state_count") or 0) > 0 or int(progress.get("pending_deferred_count") or 0) > 0


def _within_crawl_limits(progress: dict[str, Any], job: CrawlJob) -> bool:
    state_count, transition_count = _progress_counts(progress)
    return state_count < job.max_states and transition_count < job.max_transitions


def _should_continue_crawl(progress: dict[str, Any], job: CrawlJob) -> bool:
    return _has_pending_work(progress) and _within_crawl_limits(progress, job)


async def _crawl_progress(worker: Any, graph_id: str, session_id: str) -> dict[str, int]:
    return await worker._graph_builder.get_crawl_progress(graph_id, crawl_session_id=session_id)


async def _enqueue_continuation(ctx: dict, worker: Any, session_id: str) -> str:
    redis = ctx.get("redis")
    if redis is None:
        raise RuntimeError("redis context missing; cannot enqueue crawl continuation")

    job_id = f"{session_id}:slice:{uuid4().hex}"
    await redis.enqueue_job(
        "crawl_session",
        session_id,
        _job_id=job_id,
        _queue_name=worker._settings.ARQ_QUEUE_NAME,
    )
    return job_id


def _input_defaults(config_json: dict[str, Any]) -> dict[str, Any] | None:
    raw = _pick(config_json, "inputDefaults", "input_defaults")
    if not isinstance(raw, dict):
        return None

    field_patterns = _pick(raw, "field_patterns", "fieldPatterns")
    type_fallbacks = _pick(raw, "type_fallbacks", "typeFallbacks")

    return {
        "field_patterns": field_patterns if isinstance(field_patterns, dict) else {},
        "type_fallbacks": type_fallbacks if isinstance(type_fallbacks, dict) else {},
    }


def _should_generate_test_flows(config_json: dict[str, Any]) -> bool:
    value = _pick(config_json, "generateTestFlows", "generate_test_flows")
    return value is not False


def _test_flow_generation_config(config_json: dict[str, Any]) -> dict[str, Any]:
    value = _pick(config_json, "testFlowGeneration", "test_flow_generation")
    return value if isinstance(value, dict) else {}


def _flow_generation_kwargs(config_json: dict[str, Any]) -> dict[str, Any]:
    generation = _test_flow_generation_config(config_json)

    min_states = coerce_int(
        _pick(generation, "min_num_of_states_per_tf", "minNumOfStatesPerTf"),
        DEFAULT_TEST_FLOW_GENERATION_CONFIG["min_num_of_states_per_tf"],
    )
    max_states = coerce_int(
        _pick(generation, "num_of_states", "numOfStates"),
        DEFAULT_TEST_FLOW_GENERATION_CONFIG["num_of_states"],
    )
    min_flows = coerce_int(
        _pick(generation, "num_of_tf", "numOfTf"),
        DEFAULT_TEST_FLOW_GENERATION_CONFIG["num_of_tf"],
    )
    coverage_percentage = coerce_float(
        _pick(generation, "coverage_percentage", "coveragePercentage"),
        DEFAULT_TEST_FLOW_GENERATION_CONFIG["coverage_percentage"],
    )

    max_states = max(1, max_states)
    min_states = min(max_states, max(1, min_states))

    return {
        "min_num_of_states_per_tf": min_states,
        "max_num_of_states_per_tf": max_states,
        "min_num_of_tf": min(MAX_TF_TAKEN, max(1, min_flows)),
        "convergence_threshold": min(100.0, max(0.0, coverage_percentage)) / 100,
    }


def _build_payload_from_db(config_json: dict[str, Any], base_url: str, session_id: str, graph_id: str) -> dict[str, Any]:
    crawler_settings = config_json.get("crawlerSettings")
    if not isinstance(crawler_settings, dict):
        crawler_settings = {}

    settings = {
        "headless": _pick(crawler_settings, "headless"),
        "timeout_ms": _timeout_ms(config_json, crawler_settings),
        "max_states": _pick(crawler_settings, "max_states", "maxStates") or _pick(config_json, "max_states", "maxStates"),
        "max_transitions": _pick(crawler_settings, "max_transitions", "maxTransitions"),
        "max_elements_per_state": _pick(crawler_settings, "max_elements_per_state", "maxElementsPerState"),
        "max_select_options_per_element": _pick(
            crawler_settings,
            "max_select_options_per_element",
            "maxSelectOptionsPerElement",
        ),
        "max_action_repeats_per_url": _pick(crawler_settings, "max_action_repeats_per_url", "maxActionRepeatsPerUrl"),
        "action_retry_count": _pick(crawler_settings, "action_retry_count", "actionRetryCount"),
        "replay_retry_count": _pick(crawler_settings, "replay_retry_count", "replayRetryCount"),
        "popup_timeout_ms": _pick(crawler_settings, "popup_timeout_ms", "popupTimeoutMs"),
        "dom_quiet_ms": _pick(crawler_settings, "dom_quiet_ms", "domQuietMs"),
        "dom_settle_timeout_ms": _pick(crawler_settings, "dom_settle_timeout_ms", "domSettleTimeoutMs"),
        "use_dom_quiescence": _pick(crawler_settings, "use_dom_quiescence", "useDomQuiescence"),
        "page_load_state": _pick(crawler_settings, "page_load_state", "pageLoadState"),
        "click_non_http_links": _pick(crawler_settings, "click_non_http_links", "clickNonHttpLinks"),
        "defer_destructive_actions": _pick(crawler_settings, "defer_destructive_actions", "deferDestructiveActions"),
        "use_semantic_diversity": _pick(crawler_settings, "use_semantic_diversity", "useSemanticDiversity"),
        "semantic_diversity_threshold": _pick(crawler_settings, "semantic_diversity_threshold", "semanticDiversityThreshold"),
        "semantic_uncertainty_margin": _pick(crawler_settings, "semantic_uncertainty_margin", "semanticUncertaintyMargin"),
        "semantic_max_bank_size": _pick(crawler_settings, "semantic_max_bank_size", "semanticMaxBankSize"),
        "semantic_artifact_dir": _pick(crawler_settings, "semantic_artifact_dir", "semanticArtifactDir"),
        "destructive_keywords": (
            ",".join(_pick(crawler_settings, "destructive_keywords", "destructiveKeywords"))
            if isinstance(_pick(crawler_settings, "destructive_keywords", "destructiveKeywords"), list)
            else _pick(crawler_settings, "destructive_keywords", "destructiveKeywords")
        ),
    }

    return {
        "base_url": base_url,
        "session_id": session_id,
        "graph_id": graph_id,
        "settings": settings,
        "input_defaults": _input_defaults(config_json),
    }


async def crawl_session(ctx: dict, session_id: str) -> dict[str, Any]:
    db = ctx["db"]
    worker = ctx["crawler_worker"]

    async with db() as s:
        status = await get_session_status(s, session_id)
        if status == "PAUSED":
            return {"status": "paused", "session_id": session_id}
        started = await ensure_started_or_skip_aborted(s, session_id)
        if not started:
            return {"status": "aborted", "session_id": session_id}

    abort_event = asyncio.Event()
    pause_event = asyncio.Event()
    stop_requested = asyncio.Event()
    run_permission = asyncio.Event()
    run_permission.set()
    poll_task: asyncio.Task | None = None

    async def abort_poller() -> None:
        while True:
            await asyncio.sleep(1)
            async with db() as poll_s:
                current = await get_session_status(poll_s, session_id)

            if current == "ABORTED":
                abort_event.set()
                stop_requested.set()
                return

            if current == "PAUSED":
                pause_event.set()
                stop_requested.set()
                return

            run_permission.set()

    try:
        async with db() as s:
            config_json, base_url, graph_id = await fetch_job_inputs(s, session_id)
            started_at = await fetch_started_at(s, session_id)

        payload = _build_payload_from_db(config_json, base_url, session_id, graph_id)
        generate_test_flows = _should_generate_test_flows(config_json)
        job = CrawlJob.from_dict(payload, worker._settings)
        initial_progress = await _crawl_progress(worker, graph_id, session_id)
        initial_state_count, initial_transition_count = _progress_counts(initial_progress)

        remaining_timeout = _remaining_timeout_seconds(config_json, started_at)
        if remaining_timeout is not None and remaining_timeout <= TIMEOUT_SECONDS_BUFFER and _has_pending_work(initial_progress):
            raise TimeoutError(f"Crawl timed out after {_timeout_seconds(config_json)} seconds")

        slice_duration = _slice_seconds(worker._settings, remaining_timeout)
        slice_deadline_monotonic = time.monotonic() + slice_duration

        crawl_task = asyncio.create_task(
            worker.process(
                job,
                run_permission=run_permission,
                stop_requested=stop_requested,
                slice_deadline_monotonic=slice_deadline_monotonic,
                initial_state_count=initial_state_count,
                initial_transition_count=initial_transition_count,
            )
        )
        poll_task = asyncio.create_task(abort_poller())

        while True:
            done, _ = await asyncio.wait(
                {crawl_task, poll_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if poll_task in done and abort_event.is_set():
                crawl_task.cancel()
                break
            if poll_task in done and pause_event.is_set():
                break
            if crawl_task in done:
                break

        if abort_event.is_set():
            try:
                await crawl_task
            except asyncio.CancelledError:
                pass
            async with db() as s:
                await mark_finished_at_if_aborted(s, session_id)
            return {"status": "aborted", "session_id": session_id}

        state_count, transition_count = await crawl_task
        progress = await _crawl_progress(worker, graph_id, session_id)
        persisted_state_count, persisted_transition_count = _progress_counts(progress)
        state_count = max(state_count, persisted_state_count)
        transition_count = max(transition_count, persisted_transition_count)

        async with db() as s:
            status = await get_session_status(s, session_id)

        if pause_event.is_set() or status == "PAUSED":
            return {
                "status": "paused",
                "session_id": session_id,
                "state_count": state_count,
                "transition_count": transition_count,
            }

        if status == "ABORTED":
            async with db() as s:
                await mark_finished_at_if_aborted(s, session_id)
            return {"status": "aborted", "session_id": session_id}

        if _should_continue_crawl(progress, job):
            remaining_timeout = _remaining_timeout_seconds(config_json, started_at)
            if remaining_timeout is not None and remaining_timeout <= TIMEOUT_SECONDS_BUFFER:
                raise TimeoutError(f"Crawl timed out after {_timeout_seconds(config_json)} seconds")

            continuation_job_id = await _enqueue_continuation(ctx, worker, session_id)
            logger.info(
                "Crawl session %s yielded with pending work; enqueued continuation %s",
                session_id,
                continuation_job_id,
            )
            return {
                "status": "continued",
                "session_id": session_id,
                "state_count": state_count,
                "transition_count": transition_count,
                "continuation_job_id": continuation_job_id,
            }

        flow_generation_result: dict[str, Any] | None = None
        if generate_test_flows and status == "RUNNING":
            flow_generation_result = await run_find_all_flows(
                ctx,
                session_id,
                graph_id,
                **_flow_generation_kwargs(config_json),
            )

        async with db() as s:
            updated = await mark_completed_if_running(s, session_id, state_count, transition_count)
            if not updated:
                await mark_finished_at_if_aborted(s, session_id)
                return {"status": "aborted", "session_id": session_id}

        return {
            "status": "completed",
            "session_id": session_id,
            "state_count": state_count,
            "transition_count": transition_count,
            "flows": flow_generation_result,
        }

    except asyncio.CancelledError:
        async with db() as s:
            status = await get_session_status(s, session_id)
            if status == "ABORTED":
                await mark_finished_at_if_aborted(s, session_id)
            elif status == "RUNNING":
                await mark_failed_if_running(s, session_id, "Crawl worker cancelled before completion")
        raise

    except Exception as e:
        message = str(e)
        async with db() as s:
            updated = await mark_failed_if_running(s, session_id, message)
            if not updated:
                await mark_finished_at_if_aborted(s, session_id)
        logger.error("Session %s failed: %s", session_id, message, exc_info=True)
        raise

    finally:
        if poll_task is not None:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

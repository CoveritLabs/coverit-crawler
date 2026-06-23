from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.graph.queries import GET_CRAWL_PROGRESS
from src.workers.jobs.crawl_session import (
    _build_payload_from_db,
    _remaining_timeout_seconds,
    _should_continue_crawl,
    _slice_seconds,
    _timeout_seconds,
)


def test_top_level_timeout_seconds_is_overall_budget_not_browser_timeout():
    payload = _build_payload_from_db(
        {"timeoutSeconds": 3600, "crawlerSettings": {}},
        "https://books.toscrape.com/",
        "crawl-1",
        "graph-1",
    )

    assert payload["settings"]["timeout_ms"] is None
    assert _timeout_seconds({"timeoutSeconds": 3600}) == 3600


def test_crawler_settings_timeout_ms_remains_browser_timeout():
    payload = _build_payload_from_db(
        {"timeoutSeconds": 3600, "crawlerSettings": {"timeoutMs": 5000}},
        "https://books.toscrape.com/",
        "crawl-1",
        "graph-1",
    )

    assert payload["settings"]["timeout_ms"] == 5000


def test_remaining_timeout_is_calculated_from_session_start():
    started = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
    now = started + timedelta(seconds=125)

    assert _remaining_timeout_seconds({"timeoutSeconds": 3600}, started, now=now) == 3475


def test_slice_seconds_is_bounded_by_remaining_timeout():
    settings = SimpleNamespace(CRAWLER_JOB_SLICE_SECONDS=600)

    assert _slice_seconds(settings, None) == 600
    assert _slice_seconds(settings, 1200) == 600
    assert _slice_seconds(settings, 45) == 45


def test_should_continue_requires_pending_work_and_available_limits():
    job = SimpleNamespace(max_states=10, max_transitions=20)

    assert _should_continue_crawl(
        {
            "state_count": 3,
            "transition_count": 7,
            "pending_state_count": 1,
            "pending_deferred_count": 0,
        },
        job,
    )
    assert not _should_continue_crawl(
        {
            "state_count": 3,
            "transition_count": 7,
            "pending_state_count": 0,
            "pending_deferred_count": 0,
        },
        job,
    )
    assert not _should_continue_crawl(
        {
            "state_count": 10,
            "transition_count": 7,
            "pending_state_count": 1,
            "pending_deferred_count": 0,
        },
        job,
    )


def test_crawl_progress_query_uses_graph_id_and_session_frontier():
    assert "MATCH (s:State {graph_id: $session_id})" in GET_CRAWL_PROGRESS
    assert "TRANSITION {graph_id: $session_id}" in GET_CRAWL_PROGRESS
    assert "crawl_session_id: $crawl_session_id" in GET_CRAWL_PROGRESS

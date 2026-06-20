from __future__ import annotations

import json

import pytest

from src.crawler.semantic_engine.state import (
    SEMANTIC_PRIORITY_EQUIVALENT,
    SEMANTIC_PRIORITY_NOVEL,
    StateComparisonResult,
    semantic_priority_penalty,
)
from src.graph.queries import (
    ADD_STATE,
    CLAIM_NEXT_PENDING_STATE,
    ITER_SEMANTIC_PROFILES,
    SET_STATE_FRONTIER_PRIORITY,
)
from src.graph.repository import GraphRepository
from src.graph.schema import FRONTIER_CLAIM_INDEX
from src.models import AbstractState


def _comparison(
    *,
    is_novel: bool,
    is_equivalent: bool,
    matched_state_hash: str | None,
    confidence: float,
    reason: str,
) -> StateComparisonResult:
    return StateComparisonResult(
        state_hash="candidate",
        is_novel=is_novel,
        is_equivalent=is_equivalent,
        matched_state_hash=matched_state_hash,
        confidence=confidence,
        scores={"pooled_similarity": confidence},
        reason=reason,
    )


def test_semantic_priority_penalty_orders_novel_uncertain_and_equivalent_states():
    novel = _comparison(
        is_novel=True,
        is_equivalent=False,
        matched_state_hash=None,
        confidence=0.0,
        reason="novel_state",
    )
    uncertain = _comparison(
        is_novel=True,
        is_equivalent=False,
        matched_state_hash="known",
        confidence=0.82,
        reason="uncertain_comparison",
    )
    equivalent = _comparison(
        is_novel=False,
        is_equivalent=True,
        matched_state_hash="known",
        confidence=0.97,
        reason="confident_equivalence",
    )
    high_similarity = _comparison(
        is_novel=False,
        is_equivalent=True,
        matched_state_hash="known",
        confidence=0.41,
        reason="high_similarity_equivalence",
    )

    assert semantic_priority_penalty(novel) == SEMANTIC_PRIORITY_NOVEL
    assert semantic_priority_penalty(uncertain) == pytest.approx(0.82)
    assert semantic_priority_penalty(equivalent) == SEMANTIC_PRIORITY_EQUIVALENT
    assert semantic_priority_penalty(high_similarity) == SEMANTIC_PRIORITY_EQUIVALENT


def test_frontier_queries_use_priority_without_semantic_pruning_status():
    assert "coalesce(f.semantic_priority_penalty, 0.0) ASC" in CLAIM_NEXT_PENDING_STATE
    assert "f.order" in CLAIM_NEXT_PENDING_STATE
    assert "status = 'semantic_pruned'" not in SET_STATE_FRONTIER_PRIORITY
    assert "f.status IN $frontier_statuses" in ITER_SEMANTIC_PROFILES
    assert "semantic_priority_penalty" in ADD_STATE
    assert "frontier_claim" in FRONTIER_CLAIM_INDEX


class _FakeResult:
    async def single(self):
        return {"created": True}


class _FakeSession:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def run(self, query: str, **params):
        self.calls.append((query, params))
        return _FakeResult()


class _FakeDriver:
    def __init__(self):
        self.session_instance = _FakeSession()

    def session(self):
        return self.session_instance


@pytest.mark.asyncio
async def test_repository_add_state_sends_frontier_priority_metadata():
    driver = _FakeDriver()
    repo = GraphRepository(driver)  # type: ignore[arg-type]

    created = await repo.add_state(
        "graph",
        AbstractState(state_hash="s1", url="https://example.test", title="S1"),
        crawl_session_id="crawl",
        semantic_priority_penalty=1.0,
        matched_state_hash="s0",
        confidence=0.96,
        reason="confident_equivalence",
        scores={"pooled_similarity": 0.99},
    )

    assert created is True
    query, params = driver.session_instance.calls[0]
    assert query == ADD_STATE
    assert params["semantic_priority_penalty"] == 1.0
    assert params["semantic_duplicate_of"] == "s0"
    assert params["semantic_confidence"] == 0.96
    assert params["semantic_reason"] == "confident_equivalence"
    assert json.loads(params["semantic_scores_json"]) == {"pooled_similarity": 0.99}

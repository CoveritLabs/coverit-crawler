import json
from typing import Any

from neo4j import AsyncDriver

from src.graph.queries import (
    ADD_DEFERRED_WORK,
    ADD_STATE,
    ADD_TRANSITION,
    CLAIM_DEFERRED_WORK,
    CLAIM_NEXT_PENDING_STATE,
    CLEAR_SESSION,
    FIND_EQUIVALENT_TRANSITION,
    GET_ACTIONS,
    GET_CRAWL_PROGRESS,
    GET_DATA_FROM_FLOW_QUERY,
    GET_GRAPH,
    GET_LIGHTWEIGHT_FLOW_GRAPH,
    GET_REPLAY_INFO,
    GET_SEMANTIC_PROFILE,
    ITER_SEMANTIC_PROFILES,
    MARK_ACTION_ATTEMPTED,
    MARK_DEFERRED_WORK_PROCESSED,
    MARK_STATE_EXPLORED,
    MARK_STATE_PENDING,
    SET_STATE_FRONTIER_PRIORITY,
    SET_STATE_PROPS,
    TRY_INCREMENT_ACTION_REPEAT,
    UPDATE_TRANSITION,
    UPSERT_REPLAY_INFO_IF_BETTER,
    UPSERT_SEMANTIC_PROFILE,
    VERIFY_BDD_FLOW,
)
from src.models import AbstractState, AbstractTransition
from src.utils.serialization import stable_json_dumps


class GraphRepository:
    def __init__(self, driver: AsyncDriver):
        self._driver = driver

    @staticmethod
    def _normalize_prop_value(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, list):
            if all(item is None or isinstance(item, (str, int, float, bool)) for item in value):
                return value
            return stable_json_dumps(value)

        return stable_json_dumps(value)

    @staticmethod
    def _action_value_is_labelable(value: Any) -> bool:
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

        for action in actions:
            if not isinstance(action, dict):
                return False
            if not str(action.get("s") or "").strip():
                return False

        return True

    @classmethod
    def _transition_is_labelable(cls, transition: dict[str, Any]) -> bool:
        if not str(transition.get("locator_value") or "").strip():
            return False
        return cls._action_value_is_labelable(transition.get("action_value"))

    def _normalize_props(self, props: dict) -> dict:
        return {key: self._normalize_prop_value(value) for key, value in props.items()}

    @staticmethod
    def _frontier_priority_params(
        *,
        semantic_priority_penalty: float | None = None,
        matched_state_hash: str = "",
        confidence: float | None = None,
        reason: str = "",
        scores: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "semantic_priority_penalty": (
                None
                if semantic_priority_penalty is None
                else float(semantic_priority_penalty)
            ),
            "semantic_duplicate_of": matched_state_hash or "",
            "semantic_confidence": None if confidence is None else float(confidence),
            "semantic_reason": reason or "",
            "semantic_scores_json": stable_json_dumps(scores or {}) if scores else "",
        }

    async def add_state(
        self,
        graph_id: str,
        state: AbstractState,
        *,
        enqueue: bool = True,
        session_id: str = "",
        semantic_priority_penalty: float | None = None,
        matched_state_hash: str = "",
        confidence: float | None = None,
        reason: str = "",
        scores: dict[str, Any] | None = None,
    ) -> bool:
        async with self._driver.session() as session:
            result = await session.run(
                ADD_STATE,
                graph_id=graph_id,
                state_hash=state.state_hash,
                url=state.url,
                title=state.title,
                html=state.html,
                enqueue=enqueue,
                session_id=session_id,
                **self._frontier_priority_params(
                    semantic_priority_penalty=semantic_priority_penalty,
                    matched_state_hash=matched_state_hash,
                    confidence=confidence,
                    reason=reason,
                    scores=scores,
                ),
            )
            record = await result.single()
            return bool(record and record.get("created"))

    async def mark_state_pending(
        self,
        graph_id: str,
        state_hash: str,
        *,
        session_id: str = "",
        semantic_priority_penalty: float | None = None,
        matched_state_hash: str = "",
        confidence: float | None = None,
        reason: str = "",
        scores: dict[str, Any] | None = None,
    ) -> bool:
        async with self._driver.session() as session:
            result = await session.run(
                MARK_STATE_PENDING,
                graph_id=graph_id,
                session_id=session_id,
                state_hash=state_hash,
                **self._frontier_priority_params(
                    semantic_priority_penalty=semantic_priority_penalty,
                    matched_state_hash=matched_state_hash,
                    confidence=confidence,
                    reason=reason,
                    scores=scores,
                ),
            )
            record = await result.single()
            return bool(record and int(record.get("count", 0)) > 0)

    async def claim_next_pending_state(self, graph_id: str, *, session_id: str = "") -> AbstractState | None:
        async with self._driver.session() as session:
            result = await session.run(
                CLAIM_NEXT_PENDING_STATE,
                graph_id=graph_id,
                session_id=session_id,
            )
            record = await result.single()
            if not record:
                return None
            return AbstractState(
                state_hash=str(record.get("state_hash") or ""),
                url=str(record.get("url") or ""),
                title=str(record.get("title") or ""),
                html="",
            )

    async def mark_state_explored(self, graph_id: str, state_hash: str, *, session_id: str = "") -> None:
        async with self._driver.session() as session:
            await session.run(
                MARK_STATE_EXPLORED,
                graph_id=graph_id,
                session_id=session_id,
                state_hash=state_hash,
            )

    async def set_state_frontier_priority(
        self,
        graph_id: str,
        state_hash: str,
        *,
        session_id: str = "",
        semantic_priority_penalty: float = 0.0,
        matched_state_hash: str = "",
        confidence: float = 0.0,
        reason: str = "",
        scores: dict[str, Any] | None = None,
    ) -> bool:
        async with self._driver.session() as session:
            result = await session.run(
                SET_STATE_FRONTIER_PRIORITY,
                graph_id=graph_id,
                session_id=session_id,
                state_hash=state_hash,
                semantic_priority_penalty=float(semantic_priority_penalty),
                matched_state_hash=matched_state_hash,
                confidence=float(confidence),
                reason=reason,
                scores_json=stable_json_dumps(scores or {}),
            )
            record = await result.single()
            return bool(record and int(record.get("count", 0)) > 0)

    async def set_state_properties(self, graph_id: str, state_hash: str, props: dict) -> None:
        async with self._driver.session() as session:
            await session.run(
                SET_STATE_PROPS,
                graph_id=graph_id,
                state_hash=state_hash,
                props=self._normalize_props(props),
            )

    async def add_transition(self, t: AbstractTransition) -> bool:
        props = {
            "action_type": t.action_type,
            "action_description": t.action_description,
            "session_id": t.session_id,
            "locator_id": str(t.locator_id),
            "locator_value": t.locator_value,
            "action_value": t.action_value,
            "action_fingerprint": t.action_fingerprint,
            "action_stable_key": t.action_stable_key,
        }

        async with self._driver.session() as session:
            existing = await session.run(
                FIND_EQUIVALENT_TRANSITION,
                graph_id=t.graph_id,
                source_hash=t.source_state_hash,
                target_hash=t.target_state_hash,
                action_stable_key=t.action_stable_key,
                action_type=t.action_type,
                action_value=t.action_value,
                locator_value=t.locator_value,
            )
            existing_record = await existing.single()
            if existing_record and existing_record.get("transition_id"):
                canonical_transition_id = str(existing_record["transition_id"])
                t.transition_id = canonical_transition_id
                t.action_fingerprint = canonical_transition_id
                props["action_fingerprint"] = canonical_transition_id
                await session.run(
                    UPDATE_TRANSITION,
                    graph_id=t.graph_id,
                    transition_id=canonical_transition_id,
                    props=self._normalize_props(props),
                )
                return False

            result = await session.run(
                ADD_TRANSITION,
                graph_id=t.graph_id,
                source_hash=t.source_state_hash,
                target_hash=t.target_state_hash,
                transition_id=t.transition_id,
                props=self._normalize_props(props),
            )
            record = await result.single()
            return bool(record and record.get("created"))

    async def mark_action_attempted(
        self,
        graph_id: str,
        state_hash: str,
        attempt_fingerprint: str,
        *,
        session_id: str = "",
    ) -> bool:
        async with self._driver.session() as session:
            result = await session.run(
                MARK_ACTION_ATTEMPTED,
                graph_id=graph_id,
                session_id=session_id,
                state_hash=state_hash,
                attempt_fingerprint=attempt_fingerprint,
            )
            record = await result.single()
            return bool(record and record.get("created"))

    async def try_increment_action_repeat(
        self,
        graph_id: str,
        *,
        session_id: str = "",
        scope: str,
        action_key: str,
        max_repeats: int,
    ) -> bool:
        if max_repeats <= 0:
            return False
        async with self._driver.session() as session:
            result = await session.run(
                TRY_INCREMENT_ACTION_REPEAT,
                graph_id=graph_id,
                session_id=session_id,
                scope=scope,
                action_key=action_key,
                max_repeats=int(max_repeats),
            )
            record = await result.single()
            return bool(record)

    async def upsert_replay_info_if_better(
        self,
        graph_id: str,
        state_hash: str,
        props: dict[str, Any],
        score: list[Any],
    ) -> bool:
        score_values = list(score) + [999999, 999999, 999999, 999999, ""]
        async with self._driver.session() as session:
            result = await session.run(
                UPSERT_REPLAY_INFO_IF_BETTER,
                graph_id=graph_id,
                state_hash=state_hash,
                props=self._normalize_props(props),
                score_self_checkpoint=int(score_values[0]),
                score_action_count=int(score_values[1]),
                score_fallback_count=int(score_values[2]),
                score_kind_rank=int(score_values[3]),
                score_checkpoint_url=str(score_values[4] or ""),
            )
            record = await result.single()
            return bool(record and int(record.get("count", 0)) > 0)

    async def get_replay_info(self, graph_id: str, state_hash: str) -> dict[str, Any] | None:
        async with self._driver.session() as session:
            result = await session.run(
                GET_REPLAY_INFO,
                graph_id=graph_id,
                state_hash=state_hash,
            )
            record = await result.single()
            return record.data() if record else None

    async def add_deferred_work(
        self,
        graph_id: str,
        *,
        session_id: str = "",
        work_id: str,
        source_state_hash: str,
        actions_json: str,
        element_json: str,
    ) -> None:
        async with self._driver.session() as session:
            await session.run(
                ADD_DEFERRED_WORK,
                graph_id=graph_id,
                session_id=session_id,
                work_id=work_id,
                source_state_hash=source_state_hash,
                actions_json=actions_json,
                element_json=element_json,
            )

    async def claim_deferred_work(self, graph_id: str, *, session_id: str = "") -> dict[str, Any] | None:
        async with self._driver.session() as session:
            result = await session.run(
                CLAIM_DEFERRED_WORK,
                graph_id=graph_id,
                session_id=session_id,
            )
            record = await result.single()
            return record.data() if record else None

    async def mark_deferred_work_processed(self, graph_id: str, work_id: str, *, session_id: str = "") -> None:
        async with self._driver.session() as session:
            await session.run(
                MARK_DEFERRED_WORK_PROCESSED,
                graph_id=graph_id,
                session_id=session_id,
                work_id=work_id,
            )

    async def upsert_semantic_profile(
        self,
        graph_id: str,
        state_hash: str,
        payload: dict[str, Any],
    ) -> None:
        async with self._driver.session() as session:
            await session.run(
                UPSERT_SEMANTIC_PROFILE,
                graph_id=graph_id,
                state_hash=state_hash,
                payload_json=stable_json_dumps(payload),
            )

    async def get_semantic_profile(self, graph_id: str, state_hash: str) -> dict[str, Any] | None:
        async with self._driver.session() as session:
            result = await session.run(
                GET_SEMANTIC_PROFILE,
                graph_id=graph_id,
                state_hash=state_hash,
            )
            record = await result.single()
            if not record or not record.get("payload_json"):
                return None
            try:
                return json.loads(record["payload_json"])
            except Exception:
                return None

    async def iter_semantic_profiles(
        self,
        graph_id: str,
        *,
        state_hash: str,
        batch_size: int,
        session_id: str = "",
        frontier_statuses: list[str] | None = None,
    ):
        statuses = frontier_statuses or ["exploring", "explored"]
        skip = 0
        while True:
            async with self._driver.session() as session:
                result = await session.run(
                    ITER_SEMANTIC_PROFILES,
                    graph_id=graph_id,
                    session_id=session_id,
                    frontier_statuses=statuses,
                    state_hash=state_hash,
                    skip=skip,
                    limit=batch_size,
                )
                records = await result.fetch(batch_size)
            if not records:
                break
            for record in records:
                payload_json = record.get("payload_json")
                if not payload_json:
                    continue
                try:
                    payload = json.loads(payload_json)
                except Exception:
                    continue
                yield payload
            if len(records) < batch_size:
                break
            skip += batch_size

    async def get_state_graph(self, graph_id: str) -> dict:
        async with self._driver.session() as session:
            result = await session.run(GET_GRAPH, graph_id=graph_id)
            record = await result.single()
            return record.data() if record else {"states": [], "transitions": []}

    async def get_available_actions(self, graph_id: str, state_hash: str) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run(
                GET_ACTIONS,
                graph_id=graph_id,
                state_hash=state_hash,
            )
            return [r.data() for r in await result.fetch(100)]

    async def clear_session_data(self, graph_id: str) -> None:
        async with self._driver.session() as session:
            await session.run(CLEAR_SESSION, graph_id=graph_id)

    async def get_lightweight_flow_graph(self, graph_id: str) -> dict:
        async with self._driver.session() as session:
            result = await session.run(GET_LIGHTWEIGHT_FLOW_GRAPH, graph_id=graph_id)
            record = await result.single()
            if not record:
                return {"states": [], "transitions": []}
            return record.data()

    async def get_crawl_progress(self, graph_id: str, *, session_id: str = "") -> dict[str, int]:
        async with self._driver.session() as session:
            result = await session.run(
                GET_CRAWL_PROGRESS,
                graph_id=graph_id,
                session_id=session_id,
            )
            record = await result.single()
            if not record:
                return {
                    "state_count": 0,
                    "transition_count": 0,
                    "pending_state_count": 0,
                    "pending_deferred_count": 0,
                }
            return {
                "state_count": int(record.get("state_count") or 0),
                "transition_count": int(record.get("transition_count") or 0),
                "pending_state_count": int(record.get("pending_state_count") or 0),
                "pending_deferred_count": int(record.get("pending_deferred_count") or 0),
            }

    async def get_data_from_flow_query(
        self,
        graph_id: str,
        checkpoint_hash: str,
        transition_refs: list[str],
    ) -> tuple[str | None, Any, list[dict[str, Any]]]:
        async with self._driver.session() as session:
            result = await session.run(
                GET_DATA_FROM_FLOW_QUERY,
                graph_id=graph_id,
                checkpoint_hash=checkpoint_hash,
                transition_refs=transition_refs,
            )
            record = await result.single()
            if not record:
                return None, None, []
            checkpoint_url = record.get("checkpoint_url")
            checkpoint_storage_state_json = record.get("checkpoint_storage_state_json")
            transitions = sorted(record.get("transitions", []), key=lambda item: item.get("order", 0))
            return checkpoint_url, checkpoint_storage_state_json, transitions

    async def verify_bdd_flow(
        self,
        graph_id: str,
        session_id: str,
        checkpoint_hash: str,
        transition_refs: list[str],
    ) -> bool:
        if not transition_refs:
            return False

        async with self._driver.session() as session:
            result = await session.run(
                VERIFY_BDD_FLOW,
                graph_id=graph_id,
                session_id=session_id,
                checkpoint_hash=checkpoint_hash,
                transition_refs=transition_refs,
            )
            record = await result.single()
            if not record:
                return False

        transitions = sorted(
            record.get("transitions", []),
            key=lambda item: int(item.get("order", 0)),
        )
        if len(transitions) != len(transition_refs):
            return False

        expected_source_hash = checkpoint_hash
        for index, transition in enumerate(transitions):
            if transition.get("transition_id") != transition_refs[index]:
                return False
            if transition.get("source_state_hash") != expected_source_hash:
                return False
            if not self._transition_is_labelable(transition):
                return False
            expected_source_hash = str(transition.get("target_state_hash") or "")

        return True

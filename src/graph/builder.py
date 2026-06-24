from src.graph.client import Neo4jClient
from src.graph.repository import GraphRepository
from src.graph.schema import init_schema
from src.models import AbstractState, AbstractTransition


class Neo4jGraphBuilder:
    def __init__(self, uri: str, user: str, password: str):
        self._client = Neo4jClient(uri, user, password)
        self._repo: GraphRepository | None = None

    async def connect(self) -> None:
        await self._client.verify()
        await init_schema(self._client.driver)
        self._repo = GraphRepository(self._client.driver)

    async def disconnect(self) -> None:
        await self._client.close()
        self._repo = None

    @property
    def repo(self) -> GraphRepository:
        if self._repo is None:
            raise RuntimeError("graph is not connected")
        return self._repo

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
        scores: dict | None = None,
    ) -> bool:
        return await self.repo.add_state(
            graph_id,
            state,
            enqueue=enqueue,
            session_id=session_id,
            semantic_priority_penalty=semantic_priority_penalty,
            matched_state_hash=matched_state_hash,
            confidence=confidence,
            reason=reason,
            scores=scores,
        )

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
        scores: dict | None = None,
    ) -> bool:
        return await self.repo.mark_state_pending(
            graph_id,
            state_hash,
            session_id=session_id,
            semantic_priority_penalty=semantic_priority_penalty,
            matched_state_hash=matched_state_hash,
            confidence=confidence,
            reason=reason,
            scores=scores,
        )

    async def claim_next_pending_state(self, graph_id: str, *, session_id: str = "") -> AbstractState | None:
        return await self.repo.claim_next_pending_state(graph_id, session_id=session_id)

    async def mark_state_explored(self, graph_id: str, state_hash: str, *, session_id: str = "") -> None:
        await self.repo.mark_state_explored(graph_id, state_hash, session_id=session_id)

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
        scores: dict | None = None,
    ) -> bool:
        return await self.repo.set_state_frontier_priority(
            graph_id,
            state_hash,
            session_id=session_id,
            semantic_priority_penalty=semantic_priority_penalty,
            matched_state_hash=matched_state_hash,
            confidence=confidence,
            reason=reason,
            scores=scores,
        )

    async def set_state_properties(self, graph_id: str, state_hash: str, props: dict) -> None:
        await self.repo.set_state_properties(graph_id, state_hash, props)

    async def add_transition(self, transition: AbstractTransition) -> bool:
        return await self.repo.add_transition(transition)

    async def mark_action_attempted(
        self,
        graph_id: str,
        state_hash: str,
        attempt_fingerprint: str,
        *,
        session_id: str = "",
    ) -> bool:
        return await self.repo.mark_action_attempted(
            graph_id,
            state_hash,
            attempt_fingerprint,
            session_id=session_id,
        )

    async def try_increment_action_repeat(
        self,
        graph_id: str,
        *,
        scope: str,
        action_key: str,
        max_repeats: int,
        session_id: str = "",
    ) -> bool:
        return await self.repo.try_increment_action_repeat(
            graph_id,
            session_id=session_id,
            scope=scope,
            action_key=action_key,
            max_repeats=max_repeats,
        )

    async def upsert_replay_info_if_better(self, graph_id: str, state_hash: str, props: dict, score: list) -> bool:
        return await self.repo.upsert_replay_info_if_better(graph_id, state_hash, props, score)

    async def get_replay_info(self, graph_id: str, state_hash: str) -> dict | None:
        return await self.repo.get_replay_info(graph_id, state_hash)

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
        await self.repo.add_deferred_work(
            graph_id,
            session_id=session_id,
            work_id=work_id,
            source_state_hash=source_state_hash,
            actions_json=actions_json,
            element_json=element_json,
        )

    async def claim_deferred_work(self, graph_id: str, *, session_id: str = "") -> dict | None:
        return await self.repo.claim_deferred_work(graph_id, session_id=session_id)

    async def mark_deferred_work_processed(self, graph_id: str, work_id: str, *, session_id: str = "") -> None:
        await self.repo.mark_deferred_work_processed(graph_id, work_id, session_id=session_id)

    async def upsert_semantic_profile(self, graph_id: str, state_hash: str, payload: dict) -> None:
        await self.repo.upsert_semantic_profile(graph_id, state_hash, payload)

    async def get_semantic_profile(self, graph_id: str, state_hash: str) -> dict | None:
        return await self.repo.get_semantic_profile(graph_id, state_hash)

    def iter_semantic_profiles(
        self,
        graph_id: str,
        *,
        state_hash: str,
        batch_size: int,
        session_id: str = "",
        frontier_statuses: list[str] | None = None,
    ):
        return self.repo.iter_semantic_profiles(
            graph_id,
            state_hash=state_hash,
            batch_size=batch_size,
            session_id=session_id,
            frontier_statuses=frontier_statuses,
        )

    async def get_state_graph(self, graph_id: str) -> dict:
        return await self.repo.get_state_graph(graph_id)

    async def get_available_actions(self, graph_id: str, state_hash: str) -> list[dict]:
        return await self.repo.get_available_actions(graph_id, state_hash)

    async def clear_session_data(self, graph_id: str) -> None:
        await self.repo.clear_session_data(graph_id)

    async def get_lightweight_flow_graph(self, graph_id: str) -> dict:
        return await self.repo.get_lightweight_flow_graph(graph_id)

    async def get_crawl_progress(self, graph_id: str, *, session_id: str = "") -> dict[str, int]:
        return await self.repo.get_crawl_progress(graph_id, session_id=session_id)

    async def get_data_from_flow_query(
        self,
        graph_id: str,
        checkpoint_hash: str,
        transition_refs: list[str],
    ):
        return await self.repo.get_data_from_flow_query(graph_id, checkpoint_hash, transition_refs)

    async def verify_bdd_flow(
        self,
        graph_id: str,
        session_id: str,
        checkpoint_hash: str,
        transition_refs: list[str],
    ) -> bool:
        return await self.repo.verify_bdd_flow(
            graph_id,
            session_id,
            checkpoint_hash,
            transition_refs,
        )

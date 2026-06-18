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

    async def add_state(self, session_id: str, state: AbstractState) -> None:
        await self.repo.add_state(session_id, state)

    async def set_state_properties(self, session_id: str, state_hash: str, props: dict) -> None:
        await self.repo.set_state_properties(session_id, state_hash, props)

    async def add_transition(self, transition: AbstractTransition) -> None:
        await self.repo.add_transition(transition)

    async def get_state_graph(self, session_id: str) -> dict:
        return await self.repo.get_state_graph(session_id)

    async def get_available_actions(self, session_id: str, state_hash: str) -> list[dict]:
        return await self.repo.get_available_actions(session_id, state_hash)

    async def clear_session_data(self, session_id: str) -> None:
        await self.repo.clear_session_data(session_id)

    async def get_lightweight_flow_graph(self, session_id: str) -> dict:
        return await self.repo.get_lightweight_flow_graph(session_id)

    async def get_data_from_flow_query(
        self,
        session_id: str,
        checkpoint_hash: str,
        transition_refs: list[str],
    ):
        return await self.repo.get_data_from_flow_query(session_id, checkpoint_hash, transition_refs)

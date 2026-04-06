"""Neo4j graph builder for abstract state graph."""

from typing import Optional, List, Dict
from neo4j import AsyncDriver, AsyncGraphDatabase
from ..models.graph import AbstractState, AbstractTransition, CrawlAction


class Neo4jGraphBuilder:
    """Builds and manages abstract state graph in Neo4j."""

    def __init__(self, uri: str, user: str, password: str):
        self.uri = uri
        self.user = user
        self.password = password
        self.driver: Optional[AsyncDriver] = None

    async def connect(self) -> None:
        """Connect to Neo4j."""
        self.driver = AsyncGraphDatabase.driver(self.uri, auth=(self.user, self.password))
        async with self.driver.session() as session:
            result = await session.run("RETURN 1")
            await result.consume()
        print("Connected to Neo4j")

    async def disconnect(self) -> None:
        """Close connection."""
        if self.driver:
            await self.driver.close()

    async def add_state(
        self, crawl_session_id: str, state: AbstractState
    ) -> None:
        """Add state node to graph."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not initialized")

        query = """
        CREATE (s:State {
            state_id: $state_id,
            state_hash: $state_hash,
            url: $url,
            title: $title,
            session_id: $session_id,
            timestamp: timestamp()
        })
        RETURN s
        """

        async with self.driver.session() as session:
            await session.run(
                query,
                state_id=str(state.state_id),
                state_hash=state.state_hash,
                url=state.url,
                title=state.title,
                session_id=str(crawl_session_id),
            )

    async def add_transition(
        self, transition: AbstractTransition
    ) -> None:
        """Add transition edge between states."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not initialized")

        query = """
        MATCH (source:State {state_id: $source_id})
        MATCH (target:State {state_id: $target_id})
        CREATE (source)-[t:TRANSITION {
            transition_id: $transition_id,
            action_type: $action_type,
            action_description: $action_description,
            locator_value: $locator_value
        }]->(target)
        RETURN t
        """

        async with self.driver.session() as session:
            await session.run(
                query,
                source_id=str(transition.source_state_id),
                target_id=str(transition.target_state_id),
                transition_id=str(transition.transition_id),
                action_type=transition.action_type,
                action_description=transition.action_description,
                locator_value=transition.locator_value,
            )

    async def get_state_graph(
        self, crawl_session_id: str
    ) -> Dict:
        """Get entire state graph for a session."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not initialized")

        query = """
        MATCH (s:State {session_id: $session_id})
        OPTIONAL MATCH (s)-[t:TRANSITION]->(target:State)
        RETURN {
            states: collect(DISTINCT s),
            transitions: collect(DISTINCT {
                transition_id: t.transition_id,
                source_id: s.state_id,
                target_id: target.state_id,
                action_type: t.action_type
            })
        }
        """

        async with self.driver.session() as session:
            result = await session.run(query, session_id=crawl_session_id)
            record = await result.single()
            return record.value() if record else {"states": [], "transitions": []}

    async def get_available_actions(
        self, state_id: str
    ) -> List[Dict]:
        """Get available actions/transitions from a state."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not initialized")

        query = """
        MATCH (s:State {state_id: $state_id})-[t:TRANSITION]->(target:State)
        RETURN {
            transition_id: t.transition_id,
            target_state_id: target.state_id,
            action_type: t.action_type,
            action_description: t.action_description,
            locator_value: t.locator_value
        }
        """

        async with self.driver.session() as session:
            result = await session.run(query, state_id=state_id)
            records = await result.fetch(100)
            return [record.value() for record in records]

    async def clear_session_data(self, crawl_session_id: str) -> None:
        """Clear all data for a session."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not initialized")

        query = """
        MATCH (s:State {session_id: $session_id})
        DETACH DELETE s
        """

        async with self.driver.session() as session:
            await session.run(query, session_id=crawl_session_id)

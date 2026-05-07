"""Neo4j graph builder for abstract state graph."""

import logging
from typing import Optional, List, Dict
from neo4j import AsyncDriver, AsyncGraphDatabase
from ..models.graph import AbstractState, AbstractTransition, CrawlAction


logger = logging.getLogger(__name__)


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
            await self._ensure_schema(session)
        logger.info("Connected to Neo4j")

    async def _ensure_schema(self, session) -> None:
        statements = [
            "CREATE CONSTRAINT state_unique IF NOT EXISTS FOR (s:State) REQUIRE (s.session_id, s.state_hash) IS UNIQUE",
            "CREATE INDEX state_session IF NOT EXISTS FOR (s:State) ON (s.session_id)",
            "CREATE CONSTRAINT transition_unique IF NOT EXISTS FOR ()-[t:TRANSITION]-() REQUIRE (t.session_id, t.transition_id) IS UNIQUE",
            "CREATE INDEX transition_session IF NOT EXISTS FOR ()-[t:TRANSITION]-() ON (t.session_id)",
        ]
        for statement in statements:
            try:
                await session.run(statement)
            except Exception:
                pass

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

        if not crawl_session_id:
            raise ValueError("crawl_session_id is required")

        query = """
        MERGE (s:State {session_id: $session_id, state_hash: $state_hash})
        ON CREATE SET
            s.url = $url,
            s.title = $title,
            s.first_seen = timestamp(),
            s.last_seen = timestamp()
        ON MATCH SET
            s.url = $url,
            s.title = $title,
            s.last_seen = timestamp()
        RETURN s
        """

        async with self.driver.session() as session:
            await session.run(
                query,
                state_hash=state.state_hash,
                url=state.url,
                title=state.title,
                session_id=str(crawl_session_id),
            )

    async def set_state_properties(self, crawl_session_id: str, state_hash: str, props: Dict) -> None:
        if not self.driver:
            raise RuntimeError("Neo4j driver not initialized")
        if not crawl_session_id:
            raise ValueError("crawl_session_id is required")
        if not state_hash:
            raise ValueError("state_hash is required")
        if not isinstance(props, dict) or not props:
            return

        query = """
        MATCH (s:State {session_id: $session_id, state_hash: $state_hash})
        SET s += $props
        RETURN s
        """

        async with self.driver.session() as session:
            await session.run(
                query,
                session_id=str(crawl_session_id),
                state_hash=str(state_hash),
                props=props,
            )

    async def add_transition(
        self, transition: AbstractTransition
    ) -> None:
        """Add transition edge between states."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not initialized")

        if not transition.session_id:
            raise ValueError("transition.session_id is required")

        query = """
        MATCH (source:State {session_id: $session_id, state_hash: $source_hash})
        MATCH (target:State {session_id: $session_id, state_hash: $target_hash})
        MERGE (source)-[t:TRANSITION {session_id: $session_id, transition_id: $transition_id}]->(target)
        ON CREATE SET
            t.action_type = $action_type,
            t.action_description = $action_description,
            t.locator_id = $locator_id,
            t.locator_value = $locator_value,
            t.action_value = $action_value,
            t.action_fingerprint = $action_fingerprint,
            t.first_seen = timestamp(),
            t.last_seen = timestamp()
        ON MATCH SET
            t.last_seen = timestamp(),
            t.action_description = $action_description,
            t.locator_id = $locator_id,
            t.locator_value = $locator_value,
            t.action_value = $action_value,
            t.action_fingerprint = $action_fingerprint
        RETURN t
        """

        async with self.driver.session() as session:
            await session.run(
                query,
                session_id=str(transition.session_id),
                source_hash=str(transition.source_state_hash),
                target_hash=str(transition.target_state_hash),
                transition_id=str(transition.transition_id),
                action_type=transition.action_type,
                action_description=transition.action_description,
                locator_id=str(transition.locator_id),
                locator_value=transition.locator_value,
                action_value=str(getattr(transition, "action_value", "")),
                action_fingerprint=str(getattr(transition, "action_fingerprint", "")),
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
                source_hash: s.state_hash,
                target_hash: target.state_hash,
                action_type: t.action_type,
                action_value: t.action_value,
                action_fingerprint: t.action_fingerprint
            })
        }
        """

        async with self.driver.session() as session:
            result = await session.run(query, session_id=crawl_session_id)
            record = await result.single()
            return record.value() if record else {"states": [], "transitions": []}

    async def get_available_actions(
        self, crawl_session_id: str, state_hash: str
    ) -> List[Dict]:
        """Get available actions/transitions from a state."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not initialized")

        query = """
        MATCH (s:State {session_id: $session_id, state_hash: $state_hash})-[t:TRANSITION {session_id: $session_id}]->(target:State {session_id: $session_id})
        RETURN {
            transition_id: t.transition_id,
            target_state_hash: target.state_hash,
            action_type: t.action_type,
            action_description: t.action_description,
            locator_value: t.locator_value,
            action_value: t.action_value,
            action_fingerprint: t.action_fingerprint
        }
        """

        async with self.driver.session() as session:
            result = await session.run(query, session_id=str(crawl_session_id), state_hash=state_hash)
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

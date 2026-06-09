from typing import Any

from neo4j import AsyncDriver

from src.graph.queries import (
    ADD_STATE,
    SET_STATE_PROPS,
    ADD_TRANSITION,
    GET_GRAPH,
    GET_ACTIONS,
    CLEAR_SESSION,
    GET_STATES_WITH_CHECKPOINTS,
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

    def _normalize_props(self, props: dict) -> dict:
        return {key: self._normalize_prop_value(value) for key, value in props.items()}

    async def add_state(self, session_id: str, state: AbstractState) -> None:
        async with self._driver.session() as session:
            await session.run(
                ADD_STATE,
                session_id=session_id,
                state_hash=state.state_hash,
                url=state.url,
                title=state.title,
            )

    async def set_state_properties(self, session_id: str, state_hash: str, props: dict) -> None:
        async with self._driver.session() as session:
            await session.run(
                SET_STATE_PROPS,
                session_id=session_id,
                state_hash=state_hash,
                props=self._normalize_props(props),
            )

    async def add_transition(self, t: AbstractTransition) -> None:
        props = {
            "action_type": t.action_type,
            "action_description": t.action_description,
            "locator_id": str(t.locator_id),
            "locator_value": t.locator_value,
            "action_value": t.action_value,
            "action_fingerprint": t.action_fingerprint,
        }

        async with self._driver.session() as session:
            await session.run(
                ADD_TRANSITION,
                session_id=t.session_id,
                source_hash=t.source_state_hash,
                target_hash=t.target_state_hash,
                transition_id=t.transition_id,
                props=self._normalize_props(props),
            )

    async def get_state_graph(self, session_id: str) -> dict:
        async with self._driver.session() as session:
            result = await session.run(GET_GRAPH, session_id=session_id)
            record = await result.single()
            return record.data() if record else {"states": [], "transitions": []}

    async def get_available_actions(self, session_id: str, state_hash: str) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run(
                GET_ACTIONS,
                session_id=session_id,
                state_hash=state_hash,
            )
            return [r.data() for r in await result.fetch(100)]

    async def clear_session_data(self, session_id: str) -> None:
        async with self._driver.session() as session:
            await session.run(CLEAR_SESSION, session_id=session_id)

    async def get_state_graph_with_checkpoints(self, session_id: str) -> dict:
        async with self._driver.session() as session:
            result = await session.run(
                GET_STATES_WITH_CHECKPOINTS, session_id=session_id
            )
            record = await result.single()
            if not record:
                return {"states": [], "transitions": []}
            data = record.data()
            data["transitions"] = [
                t for t in data["transitions"]
                if t.get("transition_id") is not None
            ]
            return data
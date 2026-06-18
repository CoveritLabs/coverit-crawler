from neo4j import AsyncDriver

STATE_CONSTRAINT = """
CREATE CONSTRAINT state_unique IF NOT EXISTS
FOR (s:State)
REQUIRE (s.graph_id, s.state_hash) IS UNIQUE
"""

STATE_INDEX = """
CREATE INDEX state_session IF NOT EXISTS
FOR (s:State)
ON (s.graph_id)
"""

TRANSITION_CONSTRAINT = """
CREATE CONSTRAINT transition_unique IF NOT EXISTS
FOR ()-[t:TRANSITION]-()
REQUIRE (t.graph_id, t.transition_id) IS UNIQUE
"""

TRANSITION_INDEX = """
CREATE INDEX transition_session IF NOT EXISTS
FOR ()-[t:TRANSITION]-()
ON (t.graph_id)
"""


async def init_schema(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(STATE_CONSTRAINT)
        await session.run(STATE_INDEX)
        await session.run(TRANSITION_CONSTRAINT)
        await session.run(TRANSITION_INDEX)

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

DROP_LEGACY_ACTION_ATTEMPT_CONSTRAINT = "DROP CONSTRAINT action_attempt_unique IF EXISTS"
DROP_LEGACY_REPEAT_COUNTER_CONSTRAINT = "DROP CONSTRAINT action_repeat_counter_unique IF EXISTS"
DROP_LEGACY_DEFERRED_WORK_CONSTRAINT = "DROP CONSTRAINT deferred_work_unique IF EXISTS"

SEMANTIC_PROFILE_CONSTRAINT = """
CREATE CONSTRAINT semantic_profile_unique IF NOT EXISTS
FOR (p:SemanticProfile)
REQUIRE (p.graph_id, p.state_hash) IS UNIQUE
"""

FRONTIER_CONSTRAINT = """
CREATE CONSTRAINT frontier_session_unique IF NOT EXISTS
FOR (f:StateFrontier)
REQUIRE (f.graph_id, f.crawl_session_id, f.state_hash) IS UNIQUE
"""

FRONTIER_CLAIM_INDEX = """
CREATE INDEX frontier_claim IF NOT EXISTS
FOR (f:StateFrontier)
ON (
    f.graph_id,
    f.crawl_session_id,
    f.status,
    f.semantic_priority_penalty,
    f.order
)
"""

ACTION_ATTEMPT_SESSION_CONSTRAINT = """
CREATE CONSTRAINT action_attempt_session_unique IF NOT EXISTS
FOR (a:ActionAttempt)
REQUIRE (a.graph_id, a.crawl_session_id, a.state_hash, a.attempt_fingerprint) IS UNIQUE
"""

REPEAT_COUNTER_SESSION_CONSTRAINT = """
CREATE CONSTRAINT action_repeat_counter_session_unique IF NOT EXISTS
FOR (c:ActionRepeatCounter)
REQUIRE (c.graph_id, c.crawl_session_id, c.scope, c.action_key) IS UNIQUE
"""

DEFERRED_WORK_SESSION_CONSTRAINT = """
CREATE CONSTRAINT deferred_work_session_unique IF NOT EXISTS
FOR (d:DeferredWork)
REQUIRE (d.graph_id, d.crawl_session_id, d.work_id) IS UNIQUE
"""


async def init_schema(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(STATE_CONSTRAINT)
        await session.run(STATE_INDEX)
        await session.run(TRANSITION_CONSTRAINT)
        await session.run(TRANSITION_INDEX)
        await session.run(DROP_LEGACY_ACTION_ATTEMPT_CONSTRAINT)
        await session.run(DROP_LEGACY_REPEAT_COUNTER_CONSTRAINT)
        await session.run(DROP_LEGACY_DEFERRED_WORK_CONSTRAINT)
        await session.run(SEMANTIC_PROFILE_CONSTRAINT)
        await session.run(FRONTIER_CONSTRAINT)
        await session.run(FRONTIER_CLAIM_INDEX)
        await session.run(ACTION_ATTEMPT_SESSION_CONSTRAINT)
        await session.run(REPEAT_COUNTER_SESSION_CONSTRAINT)
        await session.run(DEFERRED_WORK_SESSION_CONSTRAINT)

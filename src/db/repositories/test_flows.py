import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.schemas.test_flow import TestFlow
from src.db.schemas.crawl_sessions import CrawlSession
from src.db.enums import TestFlowType  

async def create_test_flow(
    session: AsyncSession,
    session_id: str,
    checkpoint_hash: str,
    transition_refs: list[str],
    flow_type: TestFlowType | str
) -> str:
    """
    Creates a new TestFlow record. Automatically looks up the app_version_id 
    from the crawl session so you don't have to provide it manually.
    """
    stmt = select(CrawlSession.app_version_id).where(CrawlSession.crawl_session_id == session_id)
    result = await session.execute(stmt)
    app_version_id = result.scalar_one_or_none()
    
    if not app_version_id:
        raise RuntimeError(f"Could not find a valid app_version_id for crawl session: {session_id}")
        
    new_flow_id = str(uuid.uuid4())

    new_flow = TestFlow(
        id=new_flow_id,
        crawl_session_id=session_id,
        app_version_id=app_version_id,
        checkpoint_state_hash=checkpoint_hash,
        transition_refs=transition_refs,
        test_flow_type=flow_type,
        step_count=len(transition_refs)
    )
    
    session.add(new_flow)
    await session.commit()
    
    return new_flow_id


async def fetch_test_flow_details(
    session: AsyncSession, 
    session_id: str
) -> list[dict]:
    """
    Fetches the checkpoint state hash, transition refs, and flow type 
    for all TestFlows associated with a specific crawl session.
    """
    stmt = (
        select(
            TestFlow.checkpoint_state_hash,
            TestFlow.transition_refs,
            TestFlow.test_flow_type
        )
        .where(TestFlow.crawl_session_id == session_id)
    )
    
    result = await session.execute(stmt)
    
    return [
        {
            "checkpoint_state_hash": row.checkpoint_state_hash,
            "transition_refs": row.transition_refs,
            "test_flow_type": row.test_flow_type
        }
        for row in result.all()
    ]
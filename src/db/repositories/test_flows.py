from __future__ import annotations
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.enums import TestFlowType
from src.db.schemas.crawl_sessions import CrawlSession
from src.db.schemas.test_flow import TestFlow

logger = logging.getLogger(__name__)


async def create_test_flow(
    session: AsyncSession,
    session_id: str,
    checkpoint_hash: str,
    transition_refs: list[str],
    flow_type: TestFlowType | str,
) -> str:
    stmt = select(CrawlSession.app_version_id).where(
        CrawlSession.crawl_session_id == session_id
    )
    result = await session.execute(stmt)
    app_version_id = result.scalar_one_or_none()

    if not app_version_id:
        raise RuntimeError(
            f"Could not find a valid app_version_id for crawl session: {session_id}"
        )

    new_flow_id = str(uuid.uuid4())

    new_flow = TestFlow(
        id=new_flow_id,
        crawl_session_id=session_id,
        app_version_id=app_version_id,
        checkpoint_state_hash=checkpoint_hash,
        transition_refs=transition_refs,
        test_flow_type=flow_type,
        step_count=len(transition_refs),
    )

    session.add(new_flow)
    await session.commit()
    return new_flow_id


async def create_test_flows_batch(
    session: AsyncSession, session_id: str, flows_data: list[dict[str, Any]]
):
    if not flows_data:
        return []

    stmt = select(CrawlSession.app_version_id).where(
        CrawlSession.crawl_session_id == session_id
    )
    result = await session.execute(stmt)
    app_version_id = result.scalar_one_or_none()

    if not app_version_id:
        raise RuntimeError(
            f"Could not find a valid app_version_id for crawl session: {session_id}"
        )

    new_flow_ids: list[str] = []
    new_flows_instances: list[TestFlow] = []

    for flow in flows_data:
        new_id = str(uuid.uuid4())
        transitions = flow["transition_refs"]

        new_flow = TestFlow(
            id=new_id,
            crawl_session_id=session_id,
            app_version_id=app_version_id,
            checkpoint_state_hash=flow["checkpoint_hash"],
            transition_refs=transitions,
            test_flow_type=flow["flow_type"],
            step_count=len(transitions),
        )

        new_flow_ids.append(new_id)
        new_flows_instances.append(new_flow)

    session.add_all(new_flows_instances)
    await session.commit()
    return new_flow_ids


async def process_incoming_flow_payload(
    session: AsyncSession,
    payload: dict[str, Any],
    default_type: TestFlowType | str = "COVERAGE",
):
    session_id = payload.get("session_id")
    raw_flows = payload.get("flows", [])

    if not session_id:
        raise ValueError("Payload is missing a valid 'session_id'")

    mapped_flows_data = []
    for flow in raw_flows:
        mapped_flows_data.append(
            {
                "checkpoint_hash": flow["checkpoint_hash"],
                "transition_refs": flow["transition_ids"],
                "flow_type": flow.get("flow_type", default_type),
            }
        )

    return await create_test_flows_batch(
        session=session, session_id=session_id, flows_data=mapped_flows_data
    )


async def fetch_test_flow_details(
    session: AsyncSession, session_id: str
) -> list[dict[str, Any]]:
    
    stmt = select(
        TestFlow.checkpoint_state_hash,
        TestFlow.transition_refs,
        TestFlow.test_flow_type,
    ).where(TestFlow.crawl_session_id == session_id)

    result = await session.execute(stmt)

    return [
        {
            "checkpoint_state_hash": row.checkpoint_state_hash,
            "transition_refs": row.transition_refs,
            "test_flow_type": row.test_flow_type,
        }
        for row in result.all()
    ]


async def fetch_flow_editor_inputs(
    session: AsyncSession,
    flow_id: str,
) -> dict[str, Any] | None:
    stmt = select(TestFlow).where(TestFlow.id == flow_id)
    result = await session.execute(stmt)
    flow = result.scalar_one_or_none()
    if flow is None:
        return None

    crawl_session = flow.crawl_session
    graph_id = flow.app_version_id if flow.test_flow_type == TestFlowType.COVERAGE else flow.crawl_session_id

    return {
        "flow_id": flow.id,
        "crawl_session_id": flow.crawl_session_id,
        "app_version_id": flow.app_version_id,
        "graph_id": graph_id,
        "checkpoint_hash": flow.checkpoint_state_hash,
        "transition_refs": list(flow.transition_refs or []),
        "editor_steps": list(flow.editor_steps or []),
        "test_flow_type": flow.test_flow_type.value
        if isinstance(flow.test_flow_type, TestFlowType)
        else str(flow.test_flow_type or ""),
        "base_url": getattr(crawl_session, "base_url_snapshot", "") or "",
        "config": getattr(crawl_session, "config", None) or {},
    }

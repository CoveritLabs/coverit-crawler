"""
ARQ job that runs after a crawl session completes.
Single pass:
  1. find_all_flows() for all states
  2. POST all flows to the TypeScript API
"""

from __future__ import annotations

import logging
from logging import config
import os
from src.config import config
import aiohttp

from src.graph.factory import create_graph
from src.graph.flow_finder import _serialize_all_flows, find_all_flows

logger = logging.getLogger(__name__)

_API_BASE_URL = os.environ["COVERIT_API_INTERNAL_URL"].rstrip("/")



async def push_flows_to_api(session_id: str, serialized_flows: dict) -> None:
    async with aiohttp.ClientSession() as http:
        resp = await http.post(
            f"{_API_BASE_URL}/internal/sessions/{session_id}/flows",
            json={"flows": serialized_flows},
        )

        if not resp.ok:
            body = await resp.text()
            raise RuntimeError(f"API rejected flows for session {session_id}: {resp.status} {body}")
        

async def generate_flows_for_session(ctx: dict, session_id: str) -> None:
    _, graph = await create_graph(
        config.NEO4J_URI,
        config.NEO4J_USER,
        config.NEO4J_PASSWORD,
    )

    all_flows = await find_all_flows(graph, session_id=session_id)

    if not all_flows:
        logger.info("No flows found for session %s — skipping", session_id)
        return

    serialized = _serialize_all_flows(all_flows)

    await push_flows_to_api(session_id, serialized)

    logger.info(
        "Flow generation complete for session %s (%d states)",
        session_id,
        len(all_flows),
    )


async def generate_manual_crawl_flow(ctx: dict, session_id: str) -> None:
    """
    Generates flows for a manual crawl session.
    """
    _, graph = await create_graph(
        config.NEO4J_URI,
        config.NEO4J_USER,
        config.NEO4J_PASSWORD,
    )

    all_flows = await find_all_flows(graph, session_id=session_id)

    if not all_flows:
        logger.info("No flows found for manual crawl session %s — skipping", session_id)
        return

    serialized = _serialize_all_flows(all_flows)

    await push_flows_to_api(session_id, serialized)

    logger.info(
        "Flow generation complete for manual crawl session %s (%d states)",
        session_id,
        len(all_flows),
    )
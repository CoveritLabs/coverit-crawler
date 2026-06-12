"""
ARQ job that runs after a crawl session completes.
Single pass:
  1. find_all_flows() for all states
  2. POST all flows to the TypeScript API
"""

from __future__ import annotations

import logging
import os

import aiohttp

from src.graph.flow_finder import find_all_flows, _serialize_all_flows
from src.graph.factory import get_graph_repo

logger = logging.getLogger(__name__)

_API_BASE_URL = os.environ["COVERIT_API_INTERNAL_URL"].rstrip("/")


async def generate_flows_for_session(ctx: dict, session_id: str) -> None:
    graph_repo = await get_graph_repo()

    all_flows = await find_all_flows(graph_repo, session_id=session_id)

    if not all_flows:
        logger.info("No flows found for session %s — skipping", session_id)
        return

    serialized = _serialize_all_flows(all_flows)

    async with aiohttp.ClientSession() as http:
        resp = await http.post(
            f"{_API_BASE_URL}/internal/sessions/{session_id}/flows",
            json={"flows": serialized},
        )

        if not resp.ok:
            body = await resp.text()
            raise RuntimeError(
                f"API rejected flows for session {session_id}: {resp.status} {body}"
            )

    logger.info(
        "Flow generation complete for session %s (%d states)",
        session_id,
        len(all_flows),
    )
from __future__ import annotations

import logging
import os

import aiohttp

from src.config import config
from src.db.repositories.crawl_sessions import fetch_graph_id
from src.graph.factory import create_graph
from src.graph.flow_finder import find_all_flows, serialize_all_flows

logger = logging.getLogger(__name__)


def _api_base_url() -> str:
    value = os.getenv("COVERIT_API_INTERNAL_URL")
    if not value:
        raise ValueError("COVERIT_API_INTERNAL_URL is required")
    return value.rstrip("/")


async def generate_flows_for_session(ctx: dict, session_id: str, graph_id: str | None = None) -> None:
    if graph_id is None:
        db = ctx["db"]
        async with db() as s:
            graph_id = await fetch_graph_id(s, session_id)

    client, graph = await create_graph(
        config.NEO4J_URI,
        config.NEO4J_USER,
        config.NEO4J_PASSWORD,
    )

    try:
        all_flows = await find_all_flows(graph, session_id=graph_id)
        if not all_flows:
            logger.info("No flows found for session %s; skipping", session_id)
            return

        serialized = await serialize_all_flows(graph, graph_id, all_flows)

        async with aiohttp.ClientSession() as http:
            resp = await http.post(
                f"{_api_base_url()}/internal/sessions/{session_id}/flows",
                json={"flows": serialized},
            )

            if not resp.ok:
                body = await resp.text()
                raise RuntimeError(f"API rejected flows for session {session_id}: {resp.status} {body}")

        logger.info(
            "Flow generation complete for session %s (%d states)",
            session_id,
            len(all_flows),
        )
    finally:
        await client.close()

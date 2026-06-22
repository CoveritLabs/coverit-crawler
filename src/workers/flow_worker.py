from __future__ import annotations

import logging
import os
from typing import Any

import aiohttp

from src.db.repositories.crawl_sessions import fetch_graph_id
from src.graph.flow_finder import find_all_flows, serialize_all_flows

logger = logging.getLogger(__name__)


def _internal_api_base_url() -> str:
    return os.getenv("COVERIT_API_INTERNAL_URL", "http://localhost:3000/api/v1").rstrip("/")


async def _post_flows(session_id: str, flows: dict[str, list[dict[str, Any]]]) -> None:
    url = f"{_internal_api_base_url()}/internal/sessions/{session_id}/flows"
    async with aiohttp.ClientSession() as client:
        async with client.post(url, json={"flows": flows}) as response:
            if response.status >= 400:
                text = await response.text()
                raise RuntimeError(f"Failed to save flows for session {session_id}: {response.status} {text}")


async def generate_flows_for_session(ctx: dict, session_id: str) -> dict[str, Any]:
    db = ctx["db"]
    crawler_worker = ctx.get("crawler_worker")
    graph_builder = getattr(crawler_worker, "_graph_builder", None)
    if graph_builder is None:
        raise RuntimeError("crawler graph builder is not available")

    async with db() as s:
        graph_id = await fetch_graph_id(s, session_id)

    all_flows = await find_all_flows(graph_builder, session_id=graph_id)
    serialized = await serialize_all_flows(graph_builder, graph_id, all_flows)
    await _post_flows(session_id, serialized)

    flow_count = sum(len(flows) for flows in serialized.values())
    logger.info(
        "Generated %d test flows for session %s from graph %s",
        flow_count,
        session_id,
        graph_id,
    )
    return {
        "status": "completed",
        "session_id": session_id,
        "graph_id": graph_id,
        "target_state_count": len(serialized),
        "flow_count": flow_count,
    }

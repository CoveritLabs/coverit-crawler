from __future__ import annotations

import logging
from typing import Any

from src.config import config
from src.db.repositories.crawl_sessions import fetch_graph_id
from src.db.repositories.test_flows import process_incoming_flow_payload
from src.graph.factory import create_graph
from src.graph.test_flow_generation.test_flow_gen import find_all_flows

logger = logging.getLogger(__name__)


async def run_find_all_flows(
    ctx: dict,
    session_id: str,
    graph_id: str | None = None,
    min_num_of_states_per_tf: int = 3,
    max_num_of_states_per_tf: int = 20,
    convergence_threshold: float | None = None,
    min_num_of_tf: int | None = None,
) -> dict[str, Any]:
    db = ctx["db"]
    if graph_id is None:
        async with db() as s:
            graph_id = await fetch_graph_id(s, session_id)
    if not graph_id:
        raise ValueError(f"graph_id is required to generate flows for crawl session {session_id}")

    client = None
    graph = ctx.get("graph_repo")
    if graph is None:
        client, graph = await create_graph(
            config.NEO4J_URI,
            config.NEO4J_USER,
            config.NEO4J_PASSWORD,
        )

    try:
        logger.info("Finding flows for crawl session %s from graph %s", session_id, graph_id)

        flows = await find_all_flows(
            graph_repo=graph,
            session_id=graph_id,
            min_num_of_states_per_tf=min_num_of_states_per_tf,
            max_num_of_states_per_tf=max_num_of_states_per_tf,
            convergence_threshold=convergence_threshold,
            min_num_of_tf=min_num_of_tf,
        )
        if not flows:
            flows = {"flows": []}
        flows["session_id"] = session_id
        flows["graph_id"] = graph_id

        flow_count = len(flows.get("flows", []))
        if flow_count == 0:
            logger.warning(
                "No flows selected for crawl session %s; skipping BDD generation",
                session_id,
            )
            return {
                "status": "no_flows",
                "session_id": session_id,
                "graph_id": graph_id,
                "flow_count": 0,
            }

        async with db() as s:
            flow_ids = await process_incoming_flow_payload(s, flows)

        for flow_id, flow in zip(flow_ids, flows.get("flows", []), strict=False):
            flow["flow_id"] = flow_id

        flows["flow_ids"] = flow_ids

        await ctx["redis"].enqueue_job(
            "task_generate_bdd",
            payload=flows,
            _queue_name="docgen:queue",
        )

        logger.info("Generated %d flows for crawl session %s", flow_count, session_id)
        return {
            "status": "completed",
            "session_id": session_id,
            "graph_id": graph_id,
            "flow_count": flow_count,
        }
    finally:
        if client is not None:
            await client.close()

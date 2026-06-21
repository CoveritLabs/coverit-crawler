import logging

from src.db.repositories.crawl_sessions import fetch_graph_id
from src.graph.factory import create_graph
from src.graph.test_flow_generation.test_flow_gen import find_all_flows 
from src.db.repositories.test_flows import process_incoming_flow_payload
from src.config import config
logger = logging.getLogger(__name__)

async def run_find_all_flows(
    ctx: dict,
    session_id: str,
    graph_id: str | None = None,
    min_num_of_states_per_tf: int = 3,
    max_num_of_states_per_tf: int = 20,
    convergence_threshold: float | None = None,
    min_num_of_tf: int | None = None,
):
    db = ctx["db"]
    if graph_id is None:
        async with db() as s:
            graph_id = await fetch_graph_id(s, session_id)

    client, graph = await create_graph(
        config.NEO4J_URI,
        config.NEO4J_USER,
        config.NEO4J_PASSWORD,
    )

    logger.info(f"Finding flows for session: {session_id}")

    flows = await find_all_flows(
        graph_repo=graph,
        session_id=session_id,
        min_num_of_states_per_tf=min_num_of_states_per_tf,
        max_num_of_states_per_tf=max_num_of_states_per_tf,
        convergence_threshold=convergence_threshold,
        min_num_of_tf=min_num_of_tf,
    )

    async with db() as s:
        await process_incoming_flow_payload(s, flows)

    await ctx["redis"].enqueue_job(
            "task_generate_bdd",
            payload=flows,
            _queue_name="docgen:queue"
        )
    await client.close()
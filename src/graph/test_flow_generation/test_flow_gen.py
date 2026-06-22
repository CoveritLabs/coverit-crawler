from __future__ import annotations

import logging
from typing import Any
from src.db.enums import TestFlowType
from src.graph.test_flow_generation.graph import TestFlow, build_flow_graph
from src.graph.test_flow_generation.stage1_preproccessing import CandidateTFGenerator
from src.graph.test_flow_generation.stage2_selecting_best_tf import select_tfs

logger = logging.getLogger(__name__)


async def find_all_flows(
    graph_repo,
    *,
    session_id: str,
    min_num_of_states_per_tf: int = 3,
    max_num_of_states_per_tf: int = 20,
    convergence_threshold: float | None = None,
    min_num_of_tf: int | None = None,
) -> dict[str, Any]:
    """Fetch raw graph from repository, generate candidate flows, and select optimal subset."""
    raw = await graph_repo.get_lightweight_flow_graph(session_id)

    graph, root_hash = build_flow_graph(raw)
    if root_hash is None:
        logger.warning("No root found for session %s", session_id)
        return {}

    candidate_generator = CandidateTFGenerator(
        graph,
        root_hash,
        max_num_of_states_per_tf=max_num_of_states_per_tf,
    )

    candidate_generator.generate_candidate_tfs()

    candidate_generator.merge_short_tfs(
        min_num_of_states_per_tf=min_num_of_states_per_tf,
    )

    candidate_generator.append_checkpoints_to_tfs()

    candidates = candidate_generator.get_candidate_tfs()

    selected = select_tfs(
        candidates,
        transition_count=graph.transition_count,
        convergence_threshold=convergence_threshold,
        min_num_of_tf=min_num_of_tf,
        min_num_of_states_per_tf=min_num_of_states_per_tf,
    )

    logger.info(
        "find_all_flows: session=%s -> %d candidates -> %d selected",
        session_id,
        len(candidates),
        len(selected),
    )
    return get_payload(selected, session_id)


def get_payload(selected_tfs: list[TestFlow], session_id: str) -> dict[str, Any]:
    """
    Transforms the selected internal TF objects into the dictionary
    payload shape required by process_incoming_flow_payload.
    """
    return {
        "session_id": session_id,
        "flows": [
            {
                "checkpoint_hash": tf.node_path[0],
                "transition_ids": tf.transition_ids,
                "flow_type": TestFlowType.COVERAGE.value,
            }
            for tf in selected_tfs
        ],
    }

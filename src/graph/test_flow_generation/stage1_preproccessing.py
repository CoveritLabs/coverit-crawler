from __future__ import annotations
import logging

from graph import Edge, FlowGraph

logger = logging.getLogger(__name__)

from graph import TestFlow

def generate_candidate_tfs(
    graph: FlowGraph, root_hash: str, *, max_num_of_states_per_tf: int
) -> list[TestFlow]:

    candidates: list[TestFlow] = []
    seeded_transitions: set[str] = set()
    pending_starts: list[tuple[str, Edge | None]] = [(root_hash, None)]

    while pending_starts:
        start_node, seed_edge = pending_starts.pop()
        
        tf = TestFlow(
            transition_ids=[seed_edge.transition_id] if seed_edge else [],
            node_path=[seed_edge.source, start_node] if seed_edge else [start_node]
        )
        node = start_node

        while True:
            out_edges = graph.adjacency.get(node, [])
            if not out_edges:
                break

            cycle_edges = []
            forward_edges = []
            
            for e in out_edges:
                if e.target in tf.visited_nodes:
                    cycle_edges.append(e)
                else:
                    forward_edges.append(e)

            for ce in cycle_edges:
                loop_tf = TestFlow(
                    transition_ids=list(tf.transition_ids) + [ce.transition_id],
                    node_path=list(tf.node_path) + [ce.target]
                )
                candidates.append(loop_tf)

            if not forward_edges:
                break

            continue_edge, *spawn_edges = forward_edges
            
            for e in reversed(spawn_edges):
                if e.transition_id not in seeded_transitions:
                    seeded_transitions.add(e.transition_id)
                    pending_starts.append((e.target, e))
            
            seeded_transitions.add(continue_edge.transition_id)

            tf.add_step(continue_edge.transition_id, continue_edge.target)
            node = continue_edge.target

            if len(tf) >= max_num_of_states_per_tf:
                candidates.append(tf)
                tf = TestFlow(node_path=[node])

        if len(tf.transition_ids) > 0:
            candidates.append(tf)

    _assert_full_coverage(graph, candidates)
    return candidates


def _assert_full_coverage(graph: FlowGraph, candidates: list[TestFlow]) -> None:
    claimed = {tid for tf in candidates for tid in tf.transition_ids}
    missing = graph.transition_count - len(claimed)
    if missing:
        logger.error("Coverage failure: %d transitions missed", missing)


def merge_short_tfs(candidates: list[TestFlow], *, min_num_of_states_per_tf: int) -> list[TestFlow]:
    clean = [tf for tf in candidates if len(tf) >= min_num_of_states_per_tf]
    short = [tf for tf in candidates if len(tf) < min_num_of_states_per_tf]

    if not short:
        return clean

    merged: list[TestFlow] = []
    for tf in short:
        fixed = _try_forward_merge(tf, clean, min_num_of_states_per_tf) or \
                _try_backward_merge(tf, clean, min_num_of_states_per_tf)
        if fixed:
            merged.append(fixed)

    logger.info("Merged %d short TestFlows into %d longer ones", len(short), len(merged))
    logger.info("Total TestFlows after merging: %d", len(clean) + len(merged))
    logger.info("What thrown away: %d short TestFlows", len(short) - len(merged))
    return clean + merged

def _try_forward_merge(short_tf: TestFlow, clean_pool: list[TestFlow], min_len: int) -> TestFlow | None:
    if not short_tf.transition_ids:
        return None

    last_id = short_tf.transition_ids[-1]
    valid_merges = []

    for other in clean_pool:
        try:
            idx = other.transition_ids.index(last_id)
        except ValueError:
            continue

        continuation_ids = other.transition_ids[idx + 1:]
        if not continuation_ids or len(short_tf) + len(continuation_ids) < min_len:
            continue
            
        logger.debug("Merging short TF %s with continuation from %s", short_tf, other)
        
        valid_merges.append(TestFlow(
            transition_ids=short_tf.transition_ids + continuation_ids,
            node_path=short_tf.node_path + other.node_path[idx + 2:]
        ))

    return min(valid_merges, key=len, default=None)

def _try_backward_merge(short_tf: TestFlow, clean_pool: list[TestFlow], min_len: int) -> TestFlow | None:
    if not short_tf.transition_ids:
        return None

    first_id = short_tf.transition_ids[0]
    valid_merges = []

    for other in clean_pool:
        try:
            idx = other.transition_ids.index(first_id)
        except ValueError:
            continue

        prefix_ids = other.transition_ids[:idx]
        if not prefix_ids or len(prefix_ids) + len(short_tf) < min_len:
            continue


        logger.debug("Merging short TF %s with prefix from %s", short_tf, other)

        valid_merges.append(TestFlow(
            transition_ids=prefix_ids + short_tf.transition_ids,
            node_path=other.node_path[:idx + 1] + short_tf.node_path[1:]
        ))

    return min(valid_merges, key=len, default=None)
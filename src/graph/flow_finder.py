from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FlowPath:
    transition_refs: list[str]
    checkpoint_hash: str


async def find_all_flows(
    graph_repo,
    *,
    session_id: str,
    max_paths_per_state: int = 3,
    max_depth: int = 20,
) -> dict[str, list[FlowPath]]:
    raw = await graph_repo.get_lightweight_flow_graph(session_id)

    states_info: dict[str, dict] = {s["state_hash"]: s for s in raw.get("states", [])}

    if not states_info:
        logger.warning("No states found for session %s", session_id)
        return {}

    checkpoint_states = {h for h, s in states_info.items() if s.get("is_checkpoint")}
    root_hash = _find_root(states_info)

    starting_sources = set(checkpoint_states)
    if root_hash:
        starting_sources.add(root_hash)
        logger.info("Root state for session %s: %s", session_id, root_hash)

    adjacency: dict[str, list[tuple[str, str]]] = {h: [] for h in states_info}
    seen_edges: set[tuple[str, str]] = set()

    for t in raw.get("transitions", []):
        src = t.get("source_hash")
        tgt = t.get("target_hash")
        trans_id = t.get("transition_id")

        if src and tgt and trans_id:
            edge = (src, tgt)
            if edge not in seen_edges:
                seen_edges.add(edge)
                adjacency[src].append((tgt, trans_id))

    result: dict[str, list[FlowPath]] = {h: [] for h in states_info}
    recorded_sources_per_state: dict[str, set[str]] = {h: set() for h in states_info}

    queue = deque()
    for source in starting_sources:
        if source in states_info:
            queue.append((source, source, [], {source}))

    while queue:
        current, origin_cp, path, visited = queue.popleft()
        if current in checkpoint_states and current != origin_cp:
            continue
        if len(path) >= max_depth:
            continue

        for neighbor_hash, transition_id in adjacency.get(current, []):
            if neighbor_hash in visited:
                continue
            arrival_path = path + [transition_id]

            if origin_cp not in recorded_sources_per_state[neighbor_hash]:
                if len(result[neighbor_hash]) < max_paths_per_state:
                    result[neighbor_hash].append(
                        FlowPath(
                            transition_refs=arrival_path,
                            checkpoint_hash=origin_cp,
                        )
                    )
                    recorded_sources_per_state[neighbor_hash].add(origin_cp)

            new_visited = visited | {neighbor_hash}
            queue.append((neighbor_hash, origin_cp, arrival_path, new_visited))

    final = {h: flows for h, flows in result.items() if flows}

    logger.info(
        "find_all_flows: %d states with flows (session %s)",
        len(final),
        session_id,
    )
    return final


def _find_root(states: dict[str, dict]) -> str | None:
    with_ts = [(h, s) for h, s in states.items() if s.get("first_seen") is not None]
    if with_ts:
        return min(with_ts, key=lambda x: x[1]["first_seen"])[0]

    return next(iter(states), None)


async def serialize_all_flows(graph_repo, session_id: str, all_flows: dict[str, list[FlowPath]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for state_hash, flows in all_flows.items():
        result[state_hash] = []
        for flow in flows:
            checkpoint_url, _, transitions = await graph_repo.get_data_from_flow_query(
                session_id,
                flow.checkpoint_hash,
                flow.transition_refs,
            )
            path = [{"state_hash": flow.checkpoint_hash, "transition": None}]
            for transition in transitions:
                target_hash = transition.pop("target_state_hash", None)
                transition.pop("source_state_hash", None)
                transition.pop("order", None)
                if target_hash:
                    path.append({"state_hash": target_hash, "transition": transition})
            result[state_hash].append(
                {
                    "checkpoint": flow.checkpoint_hash,
                    "checkpoint_url": checkpoint_url or "",
                    "is_clipped": len(transitions) != len(flow.transition_refs),
                    "path": path,
                }
            )
    return result


def _serialize_all_flows(all_flows: dict[str, list[FlowPath]]) -> dict[str, list[dict[str, Any]]]:
    return {
        state_hash: [
            {
                "checkpoint": flow.checkpoint_hash,
                "transition_refs": flow.transition_refs,
            }
            for flow in flows
        ]
        for state_hash, flows in all_flows.items()
    }

"""
Find all simple paths from the root to every reachable
state in one DFS pass, clipped at the deepest checkpoint along each path.

Usage:
    from src.graph.flow_finder import find_all_flows

    all_flows = await find_all_flows(
        graph_repo,
        session_id="...",
        max_paths_per_state=3,   
        max_depth=20,     
    )

Returns:
    dict[state_hash, list[FlowPath]]

Each FlowPath has:
    .path        - steps from checkpoint → state as list of FlowStep
    .checkpoint  - state_hash of the path origin
    .is_clipped  - False when checkpoint == root
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FlowStep:
    """One step in a path: arrive at `state_hash` via `transition`."""
    state_hash: str
    transition: dict[str, Any] | None  


@dataclass
class FlowPath:
    path: list[FlowStep]
    checkpoint: str
    is_clipped: bool

async def find_all_flows(
    graph_repo,
    *,
    session_id: str,
    max_paths_per_state: int = 3,
    max_depth: int = 20,
) -> dict[str, list[FlowPath]]:
    """
    Single DFS pass over the session graph.
    Returns all flows for all reachable states.
    """
    raw = await graph_repo.get_state_graph_with_checkpoints(session_id)

    states: dict[str, dict] = {s["state_hash"]: s for s in raw["states"]}
    transitions: list[dict] = [
        t for t in raw["transitions"]
        if t.get("source_hash") and t.get("target_hash")
    ]

    if not states:
        logger.warning("No states found for session %s", session_id)
        return {}

    root_hash = _find_root(states)
    if root_hash is None:
        logger.warning("Could not determine root state for session %s", session_id)
        return {}
    
    logger.info("Root state for session %s: %s", session_id, root_hash)

    checkpoint_states = {h for h, s in states.items() if s.get("is_checkpoint")}

    adjacency: dict[str, list[tuple[str, dict]]] = {h: [] for h in states}
    seen_edges: set[tuple[str, str]] = set()
    for t in transitions:
        src, tgt = t["source_hash"], t["target_hash"]
        if src not in adjacency:
            continue
        edge = (src, tgt)
        if edge in seen_edges:
            continue
        seen_edges.add(edge)
        adjacency[src].append((tgt, t))

    result: dict[str, list[FlowPath]] = {h: [] for h in states}

    root_step = FlowStep(state_hash=root_hash, transition=None)

    stack: list[tuple[str, list[FlowStep], set[str]]] = [
        (root_hash, [root_step], {root_hash})
    ]

    while stack:
        current, path, path_visited = stack.pop()
        
        if len(path) >= max_depth:
            continue

        for neighbor_hash, transition in adjacency.get(current, []):
            if neighbor_hash in path_visited:
                continue
            new_visited = path_visited | {neighbor_hash}

            if neighbor_hash in checkpoint_states:
                arrival_path = path + [FlowStep(state_hash=neighbor_hash, transition=transition)]
                if len(result[neighbor_hash]) < max_paths_per_state:
                    checkpoint_hash = arrival_path[0].state_hash
                    result[neighbor_hash].append(FlowPath(
                        path=arrival_path,
                        checkpoint=checkpoint_hash,
                        is_clipped=checkpoint_hash != root_hash,
                    ))
                new_path = [FlowStep(state_hash=neighbor_hash, transition=None)]
            else:
                new_path = path + [FlowStep(state_hash=neighbor_hash, transition=transition)]
                if len(result[neighbor_hash]) < max_paths_per_state:
                    checkpoint_hash = new_path[0].state_hash
                    result[neighbor_hash].append(FlowPath(
                        path=new_path,
                        checkpoint=checkpoint_hash,
                        is_clipped=checkpoint_hash != root_hash,
                    ))

            stack.append((neighbor_hash, new_path, new_visited))

    final = {h: flows for h, flows in result.items() if flows}

    logger.info(
        "find_all_flows: %d states with flows (session %s)",
        len(final),
        session_id,
    )
    return final


def _find_root(states: dict[str, dict]) -> str | None:
    """
    The root is the state with the earliest first_seen timestamp.
    Falls back to the first state with checkpoint_kind == 'initial'.
    """

    with_ts = [(h, s) for h, s in states.items() if s.get("first_seen") is not None]
    if with_ts:
        return min(with_ts, key=lambda x: x[1]["first_seen"])[0]
    
    for h, s in states.items():
        if s.get("checkpoint_kind") == "initial":
            return h
        
    return next(iter(states), None)



def _serialize_all_flows(all_flows: dict[str, list[FlowPath]]) -> dict[str, list[dict]]:
    """
    output to plain dicts for JSON transport.
    Shape: { state_hash: [ { checkpoint, is_clipped, path: [FlowStep] } ] }
    """
    result: dict[str, list[dict]] = {}
    for state_hash, flows in all_flows.items():
        result[state_hash] = [
            {
                "checkpoint": flow.checkpoint,
                "is_clipped": flow.is_clipped,
                "path": [
                    {
                        "state_hash": step.state_hash,
                        "transition": step.transition,
                    }
                    for step in flow.path
                ],
            }
            for flow in flows
        ]
    return result
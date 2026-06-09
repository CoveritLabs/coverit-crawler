"""
flow_finder.py
--------------
Find all simple paths (no repeated states = no loops) from the root state
to a target state, clipped to start from the deepest checkpoint along each path.

Usage:
    from src.graph.flow_finder import find_flows

    flows = await find_flows(
        graph_repo,
        session_id="...",
        target_hash="...",
        max_paths=50,      
        max_depth=20,      
    )

Each returned FlowPath has:
    .full_path      - all steps root→target as (state_hash, transition) pairs
    .clipped_path   - steps from the deepest checkpoint→target
    .checkpoint     - the state_hash of the clip point (root if none found)
    .is_clipped     - False when clip point == root
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
    full_path: list[FlowStep]      
    clipped_path: list[FlowStep]    
    checkpoint: str                 
    is_clipped: bool                


async def find_flows(
    graph_repo,
    *,
    session_id: str,
    target_hash: str,
    max_paths: int = 50,
    max_depth: int = 20,
) -> list[FlowPath]:
    """
    Pull the graph for `session_id` from Neo4j and return all simple paths
    to `target_hash`, each clipped to its deepest checkpoint.
    """
    raw = await graph_repo.get_state_graph_with_checkpoints(session_id)

    states: dict[str, dict] = {s["state_hash"]: s for s in raw["states"]}
    transitions: list[dict] = [t for t in raw["transitions"] if t.get("source_hash") and t.get("target_hash")]

    if target_hash not in states:
        logger.warning("Target state %s not found in session %s", target_hash, session_id)
        return []

    root_hash = _find_root(states)
    if root_hash is None:
        logger.warning("Could not determine root state for session %s", session_id)
        return []

    if root_hash == target_hash:
        return []

   
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

    
    all_steps: list[list[FlowStep]] = []
    _dfs(
        current=root_hash,
        target=target_hash,
        adjacency=adjacency,
        visited={root_hash},
        current_path=[FlowStep(state_hash=root_hash, transition=None)],
        results=all_steps,
        max_paths=max_paths,
        max_depth=max_depth,
    )

    checkpoint_states = {h for h, s in states.items() if s.get("is_checkpoint")}

    seen_signatures: set[tuple[str, ...]] = set()
    flows: list[FlowPath] = []
    for steps in all_steps:
        flow = _build_flow(steps, root_hash, checkpoint_states)
        sig = tuple(s.state_hash for s in flow.clipped_path)
        if sig in seen_signatures:
            continue
        seen_signatures.add(sig)
        flows.append(flow)

    flows.sort(key=lambda f: len(f.clipped_path))

    logger.info(
        "Found %d flow(s) to state %s (session %s)",
        len(flows), target_hash, session_id,
    )
    return flows


def _dfs(
    *,
    current: str,
    target: str,
    adjacency: dict[str, list[tuple[str, dict]]],
    visited: set[str],
    current_path: list[FlowStep],
    results: list[list[FlowStep]],
    max_paths: int,
    max_depth: int,
) -> None:
    if len(results) >= max_paths:
        return

    if current == target:
        results.append(list(current_path))
        return

    if len(current_path) >= max_depth:
        return

    for neighbor_hash, transition in adjacency.get(current, []):
        if neighbor_hash in visited:
            continue 

        visited.add(neighbor_hash)
        current_path.append(FlowStep(state_hash=neighbor_hash, transition=transition))

        _dfs(
            current=neighbor_hash,
            target=target,
            adjacency=adjacency,
            visited=visited,
            current_path=current_path,
            results=results,
            max_paths=max_paths,
            max_depth=max_depth,
        )

        current_path.pop()
        visited.remove(neighbor_hash)


def _build_flow(
    steps: list[FlowStep],
    root_hash: str,
    checkpoint_states: set[str],
) -> FlowPath:
    """
    Walk the path from the end backwards to find the deepest checkpoint.
    Clip the path there. The target itself is excluded from checkpoint search
    (we want a checkpoint we can *start from*, not the destination).
    """
    clip_index = 0

    for i in range(len(steps) - 2, -1, -1): 
        if steps[i].state_hash in checkpoint_states:
            clip_index = i
            break

    clipped = steps[clip_index:]
    clipped = [FlowStep(state_hash=clipped[0].state_hash, transition=None)] + clipped[1:]
    checkpoint_hash = steps[clip_index].state_hash

    return FlowPath(
        full_path=steps,
        clipped_path=clipped,
        checkpoint=checkpoint_hash,
        is_clipped=(checkpoint_hash != root_hash),
    )


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

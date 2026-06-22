from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class Edge:
    source: str
    target: str
    transition_id: str

@dataclass(slots=True)
class FlowGraph:
    adjacency: dict[str, list[Edge]] = field(default_factory=dict)
    transition_count: int = 0
    checkpoints: set[str] = field(default_factory=set)

@dataclass(slots=True)
class TestFlow:
    transition_ids: list[str] = field(default_factory=list)
    node_path: list[str] = field(default_factory=list)
    visited_nodes: set[str] = field(default_factory=set)

    def __post_init__(self):
        self.visited_nodes.update(self.node_path)

    def __len__(self) -> int:
        return len(self.transition_ids)

    def add_step(self, transition_id: str, target_node: str) -> None:
        self.transition_ids.append(transition_id)
        self.node_path.append(target_node)
        self.visited_nodes.add(target_node)

def build_flow_graph(raw: dict) -> tuple[FlowGraph, str | None]:
    states = [s for s in raw.get("states", []) if s.get("state_hash")]
    graph = FlowGraph()

    graph.transition_count = sum(
        1 for t in raw.get("transitions", [])
        if t.get("source_hash") and t.get("target_hash") and t.get("transition_id")
    )

    root_hash = None
    if states:
        with_ts = [s for s in states if s.get("first_seen") is not None]
        root = min(with_ts, key=lambda x: x["first_seen"]) if with_ts else states[0]
        root_hash = root["state_hash"]

    for t in raw.get("transitions", []):
        src, tgt, tid = t.get("source_hash"), t.get("target_hash"), t.get("transition_id")
        if not (src and tgt and tid):
            continue

        graph.adjacency.setdefault(src, []).append(Edge(source=src, target=tgt, transition_id=tid))

    graph.checkpoints = {s["state_hash"] for s in states if s.get("is_checkpoint")}

    logger.info("Built graph: %d real transitions", graph.transition_count)
    return graph, root_hash

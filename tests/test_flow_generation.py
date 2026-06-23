import pytest

from src.graph.queries import GET_LIGHTWEIGHT_FLOW_GRAPH
from src.graph.test_flow_generation.graph import Edge, FlowGraph, TestFlow as GeneratedFlow
from src.graph.test_flow_generation.stage1_preproccessing import CandidateTFGenerator
from src.graph.test_flow_generation.stage2_selecting_best_tf import select_tfs
from src.graph.test_flow_generation.test_flow_gen import find_all_flows


class FakeGraphRepo:
    def __init__(self, raw: dict):
        self.raw = raw
        self.requested_session_id = None

    async def get_lightweight_flow_graph(self, session_id: str) -> dict:
        self.requested_session_id = session_id
        return self.raw


def test_lightweight_flow_graph_query_uses_graph_id_and_filters_null_transitions():
    assert "MATCH (s:State {graph_id: $session_id})" in GET_LIGHTWEIGHT_FLOW_GRAPH
    assert "TRANSITION {graph_id: $session_id}" in GET_LIGHTWEIGHT_FLOW_GRAPH
    assert "WHERE transition IS NOT NULL" in GET_LIGHTWEIGHT_FLOW_GRAPH
    assert "MATCH (s:State {session_id: $session_id})" not in GET_LIGHTWEIGHT_FLOW_GRAPH


@pytest.mark.asyncio
async def test_find_all_flows_returns_real_transitions_from_lightweight_graph():
    repo = FakeGraphRepo(
        {
            "states": [
                {"state_hash": "s0", "first_seen": 1, "is_checkpoint": True},
                {"state_hash": "s1", "first_seen": 2, "is_checkpoint": False},
                {"state_hash": "s2", "first_seen": 3, "is_checkpoint": False},
            ],
            "transitions": [
                {"source_hash": "s0", "target_hash": "s1", "transition_id": "t1"},
                {"source_hash": "s1", "target_hash": "s2", "transition_id": "t2"},
                {"source_hash": "s2", "target_hash": None, "transition_id": None},
            ],
        }
    )

    payload = await find_all_flows(
        graph_repo=repo,
        session_id="graph-1",
        min_num_of_states_per_tf=2,
        max_num_of_states_per_tf=10,
        convergence_threshold=1.0,
        min_num_of_tf=1,
    )

    assert repo.requested_session_id == "graph-1"
    assert payload["session_id"] == "graph-1"
    assert payload["flows"]
    assert set(payload["flows"][0]["transition_ids"]) == {"t1", "t2"}


def test_select_tfs_filters_by_state_count_not_transition_count():
    candidate = GeneratedFlow(transition_ids=["t1"], node_path=["s0", "s1"])

    selected = select_tfs(
        [candidate],
        transition_count=1,
        convergence_threshold=1.0,
        min_num_of_tf=1,
        min_num_of_states_per_tf=2,
    )
    rejected = select_tfs(
        [candidate],
        transition_count=1,
        convergence_threshold=1.0,
        min_num_of_tf=1,
        min_num_of_states_per_tf=3,
    )

    assert selected == [candidate]
    assert rejected == []


def test_candidate_generator_caps_flows_by_state_count():
    graph = FlowGraph(
        adjacency={
            "s0": [Edge(source="s0", target="s1", transition_id="t1")],
            "s1": [Edge(source="s1", target="s2", transition_id="t2")],
            "s2": [Edge(source="s2", target="s3", transition_id="t3")],
        },
        transition_count=3,
    )
    generator = CandidateTFGenerator(
        graph,
        "s0",
        max_num_of_states_per_tf=3,
    )

    generator.generate_candidate_tfs()

    assert generator.get_candidate_tfs()
    assert all(tf.state_count <= 3 for tf in generator.get_candidate_tfs())

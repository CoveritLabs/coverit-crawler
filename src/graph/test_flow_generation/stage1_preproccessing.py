from __future__ import annotations

import logging
from collections import deque

from src.graph.test_flow_generation.graph import Edge, FlowGraph, TestFlow
from src.models import CrawlAction
from src.crawler.fingerprints import transition_fingerprint,action_key_fingerprint
from src.models.graph import AbstractTransition
logger = logging.getLogger(__name__)


class CandidateTFGenerator:
    def __init__(self, graph: FlowGraph, root_hash: str, *, max_num_of_states_per_tf: int = 15):
        self.graph = graph
        self.root_hash = root_hash
        self.max_num_of_states_per_tf = max_num_of_states_per_tf
        self.candidates: list[TestFlow] = []

    def generate_candidate_tfs(self):
        seeded_transitions: set[str] = set()
        pending_starts: list[tuple[str, Edge | None]] = [(self.root_hash, None)]

        while pending_starts:
            start_node, seed_edge = pending_starts.pop()

            tf = TestFlow(
                transition_ids=[seed_edge.transition_id] if seed_edge else [],
                node_path=[seed_edge.source, start_node] if seed_edge else [start_node]
            )
            node = start_node

            while True:
                out_edges = self.graph.adjacency.get(node, [])
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
                    self.candidates.append(loop_tf)

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

                if tf.state_count >= self.max_num_of_states_per_tf:
                    self.candidates.append(tf)
                    tf = TestFlow(node_path=[node])

            if len(tf.transition_ids) > 0:
                self.candidates.append(tf)

        self._assert_full_coverage()

    def _assert_full_coverage(self) -> None:
        claimed = {tid for tf in self.candidates for tid in tf.transition_ids}
        missing = self.graph.transition_count - len(claimed)
        if missing:
            logger.error("Coverage failure: %d transitions missed", missing)

    def merge_short_tfs(self, *, min_num_of_states_per_tf: int):
        clean = [tf for tf in self.candidates if tf.state_count >= min_num_of_states_per_tf]
        short = [tf for tf in self.candidates if tf.state_count < min_num_of_states_per_tf]

        if not short:
            return clean

        merged: list[TestFlow] = []
        for tf in short:
            fixed = self._try_forward_merge(tf, clean, min_num_of_states_per_tf) or \
                    self._try_backward_merge(tf, clean, min_num_of_states_per_tf)
            if fixed:
                merged.append(fixed)

        logger.info("Merged %d short TestFlows into %d longer ones", len(short), len(merged))
        logger.info("Total TestFlows after merging: %d", len(clean) + len(merged))
        logger.info("What thrown away: %d short TestFlows", len(short) - len(merged))
        self.candidates = clean + merged

    def _try_forward_merge(self, short_tf: TestFlow, clean_pool: list[TestFlow], min_len: int) -> TestFlow | None:
        if not short_tf.node_path:
            return None

        target_node = short_tf.node_path[-1]
        valid_merges = []

        for other in clean_pool:
            indices = [i for i, n in enumerate(other.node_path) if n == target_node]  
            for idx in indices:
                continuation_nodes = other.node_path[idx + 1:]
                continuation_transitions = other.transition_ids[idx:]
                
                if not continuation_nodes or (len(short_tf.node_path) + len(continuation_nodes)) < min_len:
                    continue
                
                logger.debug("Merging short TF %s with continuation from %s at index %d", short_tf, other, idx)
                
                valid_merges.append(TestFlow(
                    transition_ids=short_tf.transition_ids + continuation_transitions,
                    node_path=short_tf.node_path + continuation_nodes
                ))

        return min(valid_merges, key=lambda tf: len(tf.node_path), default=None)

    def _try_backward_merge(self, short_tf: TestFlow, clean_pool: list[TestFlow], min_len: int) -> TestFlow | None:
        if not short_tf.node_path:
            return None

        target_node = short_tf.node_path[0]
        valid_merges = []

        for other in clean_pool:
            indices = [i for i, n in enumerate(other.node_path) if n == target_node]
            for idx in indices:
                prefix_nodes = other.node_path[:idx]
                prefix_transitions = other.transition_ids[:idx]
                
                if not prefix_nodes or (len(prefix_nodes) + len(short_tf.node_path)) < min_len:
                    continue

                logger.debug("Merging short TF %s with prefix from %s at index %d", short_tf, other, idx)

                valid_merges.append(TestFlow(
                    transition_ids=prefix_transitions + short_tf.transition_ids,
                    node_path=prefix_nodes + short_tf.node_path
                ))

        return min(valid_merges, key=lambda tf: len(tf.node_path), default=None)
    
    def append_checkpoints_to_tfs(self) -> None:
        valid_starts = set(self.graph.checkpoints.keys())
        valid_starts.add(self.root_hash)
        targets = {
            tf.node_path[0] for tf in self.candidates
            if tf.node_path and tf.node_path[0] not in valid_starts
        }

        if not targets:
            return

        found_prefixes: dict[str, tuple[list[str], list[str]]] = {}
        queue = deque()

        visited = set(valid_starts)

        for start_node in valid_starts:
            queue.append((start_node, [], [start_node]))

        while queue and len(found_prefixes) < len(targets):
            current_node, trans_path, node_path = queue.popleft()

            for edge in self.graph.adjacency.get(current_node, []):
                neighbor = edge.target

                if neighbor in visited:
                    continue

                visited.add(neighbor)

                new_trans_path = trans_path + [edge.transition_id]
                new_node_path = node_path + [neighbor]

                if neighbor in targets:
                    found_prefixes[neighbor] = (new_trans_path, new_node_path)
                    if len(found_prefixes) == len(targets):
                        break

                if neighbor not in valid_starts:
                    queue.append((neighbor, new_trans_path, new_node_path))

        for tf in self.candidates:
            if not tf.node_path:
                continue

            start_node = tf.node_path[0]

            if start_node in found_prefixes:
                prefix_trans, prefix_nodes = found_prefixes[start_node]
                tf.transition_ids = prefix_trans + tf.transition_ids
                tf.node_path = prefix_nodes[:-1] + tf.node_path
                logger.info("Found prefix for %s and appended it to it",start_node)

            elif start_node in targets:
                logger.warning("Could not find a path from any checkpoint to node %s", start_node)



    async def append_login_to_tfs(self, *, login_hash: str | None, graph_repo,graph_id: str,session_id: str) -> list[TestFlow]:
        if not login_hash:
            logger.warning("No login_hash provided; skipping login prefixing")
            return self.candidates

        for tf in self.candidates:
            if not tf.node_path:
                continue

            start_node = tf.node_path[0]

            if start_node == login_hash:
                logger.info("TF %s already starts with login node; no prefix needed", tf)
                continue

            """
            Add transition navigate from login_hash to start_node given that we already called
            append_checkpoints_to_tfs() and thus start_node is guaranteed to be a checkpoint.
            """ 
            
            action = CrawlAction(action_type="navigate", value=self.graph.checkpoints.get(start_node) or "", description="Navigate to URL")

            fp = transition_fingerprint(
                graph_id=graph_id,
                source_state_hash=login_hash,
                target_state_hash=start_node,
                action=action,
            )
            transition = AbstractTransition(
                session_id=session_id,
                graph_id=graph_id,
                transition_id=fp,
                source_state_hash=login_hash,
                target_state_hash=start_node,
                action_type="navigate",
                action_description=action.description,
                locator_id="",
                locator_value="",
                action_value=action.value,
                action_fingerprint=fp,
                action_stable_key=action_key_fingerprint(action),
            )
            await graph_repo.add_transition(transition)

            """
            Prepend the login transition to the TestFlow.
            """
            tf.transition_ids.insert(0, transition.transition_id)
            tf.node_path.insert(0, login_hash)

        return self.candidates

    def get_candidate_tfs(self) -> list[TestFlow]:
        return self.candidates
    


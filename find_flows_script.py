
"""
Run this from the coverit-crawler root after populating Neo4j via example_usage.py.
this script is to call find_all_flows() for a given session and print the results, for testing/debugging purposes
it uses the neo4j graph that is already populated by the crawler, so it doesn't require running the full crawl flow

Usage:
    python find_flows_script.py <session_id>

What it checks:
    - find_all_flows() runs without error
    - Every state with a flow has at least one path
    - No path exceeds max_depth
    - No path contains duplicate state hashes (no loops)
    - Checkpoint reset works: clipped paths don't contain states from before the checkpoint
    - Serialization produces valid JSON
"""

from __future__ import annotations

import asyncio
import json
import sys


async def main(session_id: str) -> None:
    from src.graph.factory import create_graph
    from src.config import config
    from src.graph.flow_finder import find_all_flows, _serialize_all_flows

    print(f"\nConnecting to Neo4j...")
    client, graph_repo = await create_graph(
        config.NEO4J_URI,
        config.NEO4J_USER,
        config.NEO4J_PASSWORD,
    )

    try:
        print(f"Running find_all_flows for session: {session_id}\n")
        all_flows = await find_all_flows(
            graph_repo,
            session_id=session_id,
            max_paths_per_state=3,
            max_depth=20,
        )

        if not all_flows:
            print("ERROR: No flows returned — is Neo4j populated for this session?")
            return

        # ----------------------------------------------------------------
        # Basic stats
        # ----------------------------------------------------------------
        total_flows = sum(len(flows) for flows in all_flows.values())
        clipped_count = sum(
            1 for flows in all_flows.values()
            for f in flows if f.is_clipped
        )
        path_lengths = [
            len(f.path)
            for flows in all_flows.values()
            for f in flows
        ]

        print(f"States with flows : {len(all_flows)}")
        print(f"Total flows       : {total_flows}")
        print(f"Clipped flows     : {clipped_count}")
        print(f"Min path length   : {min(path_lengths)}")
        print(f"Max path length   : {max(path_lengths)}")
        print(f"Avg path length   : {sum(path_lengths) / len(path_lengths):.1f}")

        # ----------------------------------------------------------------
        # Correctness checks
        # ----------------------------------------------------------------
        errors: list[str] = []

        for state_hash, flows in all_flows.items():
            if len(flows) == 0:
                errors.append(f"State {state_hash[:8]} has empty flow list")
                continue

            if len(flows) > 3:
                errors.append(f"State {state_hash[:8]} has {len(flows)} flows — exceeds max_paths_per_state=3")

            for i, flow in enumerate(flows):
                path_hashes = [step.state_hash for step in flow.path]

                # No loops
                if len(path_hashes) != len(set(path_hashes)):
                    errors.append(f"State {state_hash[:8]} flow {i}: duplicate state in path (loop detected)")

                # Path ends at target
                if path_hashes[-1] != state_hash:
                    errors.append(f"State {state_hash[:8]} flow {i}: path does not end at target state")

                # Checkpoint is first step
                if flow.path[0].state_hash != flow.checkpoint:
                    errors.append(f"State {state_hash[:8]} flow {i}: checkpoint mismatch with path[0]")

                # First step has no transition (it's the checkpoint)
                if flow.path[0].transition is not None:
                    errors.append(f"State {state_hash[:8]} flow {i}: path[0] should have transition=None")

                # All other steps have a transition
                for j, step in enumerate(flow.path[1:], 1):
                    if step.transition is None:
                        errors.append(f"State {state_hash[:8]} flow {i}: step {j} missing transition")

                # Max depth
                if len(flow.path) > 20:
                    errors.append(f"State {state_hash[:8]} flow {i}: path length {len(flow.path)} exceeds max_depth=20")

        # ----------------------------------------------------------------
        # Serialization check
        # ----------------------------------------------------------------
        try:
            serialized = _serialize_all_flows(all_flows)
            json_str = json.dumps(serialized)
            reparsed = json.loads(json_str)
            assert len(reparsed) == len(all_flows), "Serialized state count mismatch"
            print(f"\nSerialized payload size: {len(json_str) / 1024:.1f} KB")
        except Exception as e:
            errors.append(f"Serialization failed: {e}")

        # ----------------------------------------------------------------
        # Sample output — first flow for first 3 states
        # ----------------------------------------------------------------
        print("\n---all flows for all states ---")
        for state_hash, flows in list(all_flows.items()):
            for flow in flows:
                print(f"\nTarget : {state_hash}")
                print(f"Clipped: {flow.is_clipped}  |  Checkpoint: {flow.checkpoint}")
                print(f"Steps  : {len(flow.path)}")
                for j, step in enumerate(flow.path):
                    action = step.transition.get("action_type", "-") if step.transition else "checkpoint"
                    desc = step.transition.get("action_description", "") if step.transition else ""
                    print(f"  [{j}] {action:12} {step.state_hash}  {desc}")

        # ----------------------------------------------------------------
        # Result
        # ----------------------------------------------------------------
        print("\n--- Checks ---")
        if errors:
            for err in errors:
                print(f"  FAIL: {err}")
            print(f"\n{len(errors)} check(s) failed.")
        else:
            print("  All checks passed.")

    finally:
        await client.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python test_find_all_flows.py <session_id>")
        sys.exit(1)

    asyncio.run(main(sys.argv[1]))
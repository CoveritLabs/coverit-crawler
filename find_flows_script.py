
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
        path_lengths = [
            len(flows)
            for flows in all_flows.values()
        ]

        print(f"States with flows : {len(all_flows)}")
        print(f"Total flows       : {total_flows}")
        print(f"Min path length   : {min(path_lengths)}")
        print(f"Max path length   : {max(path_lengths)}")
        print(f"Avg path length   : {sum(path_lengths) / len(path_lengths):.1f}")

        # ----------------------------------------------------------------
        # Correctness checks
        # ----------------------------------------------------------------
        errors: list[str] = []

        for state_hash, flows in all_flows.items():
            if not flows:
                errors.append(f"State {state_hash[:8]} has no flows")
                continue

            for flow in flows:
                if len(flow.transition_refs) > 20:
                    errors.append(f"State {state_hash[:8]} has a long path ({len(flow.transition_refs)} steps)")

                if len(set(flow.transition_refs)) != len(flow.transition_refs):
                    errors.append(f"State {state_hash[:8]} has duplicate states in its path (loop detected)")

                if flow.checkpoint_hash and flow.checkpoint_hash in flow.transition_refs:
                    errors.append(f"State {state_hash[:8]} has checkpoint {flow.checkpoint_hash[:8]} in its path (checkpoint reset failed)")

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
        # Sample output print
        # ----------------------------------------------------------------
        print("\n---all flows for all states ---")
        for state_hash, flows in list(all_flows.items()):
            for flow in flows:
                print(f"State {state_hash} <- checkpoint {flow.checkpoint_hash} via {[t for t in flow.transition_refs]}")

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
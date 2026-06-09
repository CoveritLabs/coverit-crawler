"""
example_flows.py
----------------
Drop-in example showing how to call find_flows against a live session.
Run from the repo root:

    python example_flows.py
"""

import asyncio
import logging

from src.config import config
from src.graph import create_graph
from src.graph.flow_finder import find_flows

logging.basicConfig(level=logging.INFO)

SESSION_ID  = "5adeca26-d6e3-41a7-b528-ba308614444b"
TARGET_HASH = "97f69d333c60b1d384fdc968a8bc0f8a0669fdcb76d105d79fb7094232f67bdd"


async def main() -> None:
    client, graph = await create_graph(
        config.NEO4J_URI,
        config.NEO4J_USER,
        config.NEO4J_PASSWORD,
    )

    try:
        flows = await find_flows(
            graph,
            session_id=SESSION_ID,
            target_hash=TARGET_HASH,
            max_paths=50,
            max_depth=20,
        )

        print(f"\nFound {len(flows)} flow(s) to {TARGET_HASH}\n")

        for i, flow in enumerate(flows, 1):
            clip_note = (
                f"clipped at checkpoint {flow.checkpoint}"
                if flow.is_clipped
                else "from root"
            )
            print(f"── Flow {i}  ({len(flow.clipped_path)} steps, {clip_note}) ──")

            for step in flow.clipped_path:
                if step.transition is None:
                    print(f"  START  {step.state_hash}")
                else:
                    t = step.transition
                    print(
                        f"  → [{t.get('action_type','?')}]  "
                        f"{t.get('action_description') or t.get('locator_value', '')}  "
                        f"  ▶  {step.state_hash}"
                    )
            print()

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())